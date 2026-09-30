"""
La matriz de usuarios existentes y la readmisión en el mismo tenant (A03).

Qué se fija aquí
---------------
Antes de A03, crear un usuario cuyo nombre ya existía devolvía un 409 con una
frase y nada más. Esa frase servía para decir "está tomado" y para nada más: un
`IntegrityError` no distingue entre quien trabaja aquí, quien está suspendido y
quien fue retirado hace un año, y esas tres situaciones tienen tres salidas
distintas. Estos tests fijan las cuatro clasificaciones y la única de ellas que
tiene recuperación.

Por qué la restauración es la misma fila
----------------------------------------
`uq_user_company_user_company` es una restricción **completa**, no parcial, y la
migración 0004 dice por qué: dejarla parcial habilitaría una reincorporación de
identidad que A01 difirió expresamente. Así que la fila con lápida sigue ahí y
readmitir es levantarle la lápida. Insertar una segunda pertenencia para
esquivar la restricción es justo lo que FR-07 prohíbe, y aquí se comprueba
contando filas.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from app.database import async_session_maker


pytestmark = pytest.mark.integration


BUENA = "Contrasena10"  # 12 caracteres: por encima del mínimo del servidor.


async def _crear(cliente, seeded, *, username: str, rol: str = "supervisor", password=BUENA):
    return await cliente.post(
        "/api/route/users",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "first_name": "Nueva",
            "last_name": "Persona",
            "password": password,
            "gender": True,
            "role_id": seeded.alpha.roles[rol],
        },
    )


async def _pertenencias(company_id: int, user_id: int) -> list[dict]:
    async with async_session_maker() as session:
        filas = await session.execute(
            text(
                "SELECT id, is_active, deleted_at, role_id FROM user_company "
                "WHERE company_id = :c AND user_id = :u ORDER BY id"
            ),
            {"c": company_id, "u": user_id},
        )
        return [dict(f._mapping) for f in filas]


# ── Contraseña: el servidor manda ───────────────────────────────────────────


@pytest.mark.parametrize("largo", [6, 9])
async def test_a_short_password_is_rejected_with_a_field_error(
    seeded, alpha_client, largo,
):
    """Casos borde 1 y 2: el servidor rechaza, y dice **en qué campo**.

    El 422 de Pydantic trae `detail[].loc`, que es lo que permite a la pantalla
    llevar el mensaje al campo de la contraseña en vez de enseñar un fallo
    genérico. Sin esa estructura, la interfaz no tendría dónde ponerlo.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(
        alpha_client, seeded, username="corta", password="a" * largo
    )

    assert respuesta.status_code == 422, respuesta.text
    detalle = respuesta.json()["detail"]
    assert isinstance(detalle, list)
    campos = [d["loc"][-1] for d in detalle]
    assert "password" in campos, detalle


async def test_the_minimum_length_is_accepted(seeded, alpha_client):
    """Caso borde 3: diez caracteres pasan. El mínimo es diez, no once."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(
        alpha_client, seeded, username="justos", password="a" * 10
    )
    assert respuesta.status_code in (200, 201), respuesta.text


# ── La matriz de usuarios existentes ────────────────────────────────────────


async def test_an_active_same_tenant_username_is_named_and_not_duplicated(
    seeded, alpha_client,
):
    """D-A03-02: ya trabaja aquí. Se explica, y no se toca nada."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    existente = seeded.alpha.users["supervisor"]

    async with async_session_maker() as session:
        antes = await session.scalar(
            text("SELECT count(*) FROM user_company WHERE company_id = :c"),
            {"c": seeded.alpha.id},
        )
        nombre = await session.scalar(
            text("SELECT username FROM \"user\" WHERE id = :i"),
            {"i": existente.id},
        )

    respuesta = await _crear(alpha_client, seeded, username=nombre)
    assert respuesta.status_code == 409, respuesta.text
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "same_tenant_active"
    assert "already exists in this company" in detalle["message"]
    # No se ofrece readmitir lo que no se retiró.
    assert detalle.get("user_id") == existente.id

    async with async_session_maker() as session:
        despues = await session.scalar(
            text("SELECT count(*) FROM user_company WHERE company_id = :c"),
            {"c": seeded.alpha.id},
        )
    assert despues == antes, "un conflicto no puede crear nada"


async def test_a_deactivated_same_tenant_user_is_pointed_at_reactivate(
    seeded, alpha_client,
):
    """D-A03-03: suspendido se reactiva, no se recrea.

    Y se distingue de retirado: son dos estados con dos salidas, y confundirlos
    llevaría a readmitir a alguien que nunca se fue.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (await _crear(alpha_client, seeded, username="suspendido")).json()

    baja = await alpha_client.put(
        f"/api/route/users/{creado['id']}/access", json={"is_active": False}
    )
    assert baja.status_code == 200, baja.text

    respuesta = await _crear(alpha_client, seeded, username="suspendido")
    assert respuesta.status_code == 409, respuesta.text
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "same_tenant_inactive"
    assert "reactivate" in detalle["message"].lower()

    # Sigue habiendo una sola pertenencia, y sigue sin lápida.
    filas = await _pertenencias(seeded.alpha.id, creado["id"])
    assert len(filas) == 1
    assert filas[0]["deleted_at"] is None
    assert filas[0]["is_active"] is False


async def test_a_removed_same_tenant_user_offers_re_enrollment(
    seeded, alpha_client,
):
    """D-A03-04: estuvo aquí y se le retiró el acceso. Eso **sí** tiene salida.

    El conflicto trae el identificador y el nombre visible, que es lo mínimo
    para que la pantalla pueda ofrecer readmitir a alguien concreto. Son datos
    que esta compañía ya ve en su lista de usuarios.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (await _crear(alpha_client, seeded, username="retirado")).json()

    baja = await alpha_client.delete(f"/api/route/users/{creado['id']}")
    assert baja.status_code in (200, 204), baja.text

    respuesta = await _crear(alpha_client, seeded, username="retirado")
    assert respuesta.status_code == 409, respuesta.text
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "same_tenant_removed"
    assert detalle["user_id"] == creado["id"]
    assert detalle["display_name"], "sin nombre la confirmación no identifica a nadie"
    # Nada de vocabulario interno en lo que ve la persona (D-A03-04).
    for interno in ("user_company", "deleted_at", "tombstone", "membership"):
        assert interno not in detalle["message"].lower()


async def test_an_identity_from_another_tenant_says_only_that_it_is_unavailable(
    seeded, alpha_client, beta_client,
):
    """D-A03-05 y FR-10: no se enumera a los demás clientes.

    El nombre existe en la plataforma y esta compañía no tiene historia con él.
    Se responde que no está disponible — que es cierto— y **no** se dice de
    quién es, ni cuántas pertenencias tiene, ni que exista en otro sitio.
    """
    await beta_client.login(seeded.beta.users["route_admin"].email)
    ajeno = await beta_client.post(
        "/api/route/users",
        json={
            "username": "soloenbeta",
            "email": "soloenbeta@example.com",
            "first_name": "Ajena",
            "last_name": "Persona",
            "password": BUENA,
            "gender": True,
            "role_id": seeded.beta.roles["supervisor"],
        },
    )
    assert ajeno.status_code in (200, 201), ajeno.text
    id_ajeno = ajeno.json()["id"]

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear(alpha_client, seeded, username="soloenbeta")

    assert respuesta.status_code == 409, respuesta.text
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "username_unavailable"
    assert detalle["message"] == "This username is unavailable."
    # Ni el identificador, ni el nombre, ni rastro de la otra compañía.
    assert "user_id" not in detalle, detalle
    assert "display_name" not in detalle, detalle

    # Y la pertenencia del otro tenant no se toca.
    filas = await _pertenencias(seeded.beta.id, id_ajeno)
    assert len(filas) == 1 and filas[0]["deleted_at"] is None


# ── La readmisión ───────────────────────────────────────────────────────────


async def _retirar(cliente, seeded, username: str) -> int:
    creado = (await _crear(cliente, seeded, username=username)).json()
    await cliente.delete(f"/api/route/users/{creado['id']}")
    return creado["id"]


async def test_re_enrollment_restores_the_same_row_and_the_same_identity(
    seeded, alpha_client,
):
    """FR-07: la misma identidad y **la misma fila**.

    Se cuenta antes y después: una pertenencia, no dos. Y el `user.id` es el
    mismo, así que no hay una segunda identidad de plataforma.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "vuelve")

    antes = await _pertenencias(seeded.alpha.id, user_id)
    assert len(antes) == 1 and antes[0]["deleted_at"] is not None

    respuesta = await alpha_client.post(
        f"/api/route/users/{user_id}/reenrollment",
        json={"role_id": seeded.alpha.roles["route_admin"]},
    )
    assert respuesta.status_code == 200, respuesta.text
    devuelto = respuesta.json()

    assert devuelto["id"] == user_id, "la identidad del núcleo se conserva"
    assert devuelto["is_active"] is True, "y vuelve visible como activa"

    despues = await _pertenencias(seeded.alpha.id, user_id)
    assert len(despues) == 1, "no se crea una segunda pertenencia"
    assert despues[0]["id"] == antes[0]["id"], "es la misma fila, restaurada"
    assert despues[0]["deleted_at"] is None
    assert despues[0]["is_active"] is True
    assert despues[0]["role_id"] == seeded.alpha.roles["route_admin"], (
        "se aplica el rol que eligió el administrador"
    )

    async with async_session_maker() as session:
        identidades = await session.scalar(
            text("SELECT count(*) FROM \"user\" WHERE username = 'vuelve'")
        )
    assert identidades == 1, "no se duplica la identidad de plataforma"


async def test_re_enrollment_is_audited_without_the_credential(
    seeded, alpha_client,
):
    """§12: queda el antes y el después, y **nada** de la contraseña.

    Ni el valor ni su hash son datos de auditoría. Se comprueba sobre el texto
    completo del evento, no sobre los campos que yo espere: si alguien añadiera
    la credencial a `changes` mañana, esto tiene que fallar.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "auditada")
    await alpha_client.post(
        f"/api/route/users/{user_id}/reenrollment",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )

    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT actor_user_id, company_id, action, changes::text AS ch "
                    "FROM audit_event WHERE company_id = :c "
                    "AND entity_type = 'user_company' AND action = 'reenroll' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"c": seeded.alpha.id},
            )
        ).one()

    assert fila.actor_user_id == seeded.alpha.users["route_admin"].id
    cambios = json.loads(fila.ch)
    assert cambios["membership"] == {"old": "removed", "new": "active"}
    assert cambios["role_id"]["new"] == seeded.alpha.roles["supervisor"]

    crudo = fila.ch.lower()
    assert BUENA.lower() not in crudo, "la contraseña no es un dato de auditoría"
    for prohibido in ("password", "hash", "token", "secret"):
        assert prohibido not in crudo, f"{prohibido} no puede aparecer"


async def test_re_enrollment_only_applies_route_roles(seeded, alpha_client):
    """D-A03-06 y FR-08: readmitir no es una puerta a los roles del núcleo.

    El servidor decide, no la pantalla: se llama al endpoint directamente con
    cada rol del núcleo y los cuatro se rechazan.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "escalada")

    for rol in ("owner", "admin", "manager", "viewer"):
        respuesta = await alpha_client.post(
            f"/api/route/users/{user_id}/reenrollment",
            json={"role_id": seeded.alpha.roles[rol]},
        )
        assert respuesta.status_code == 403, f"{rol}: {respuesta.text}"

    # Y sigue retirada: un rechazo no readmite a medias.
    filas = await _pertenencias(seeded.alpha.id, user_id)
    assert filas[0]["deleted_at"] is not None


async def test_re_enrolling_someone_who_is_not_removed_is_refused(
    seeded, alpha_client,
):
    """Readmitir sólo aplica a quien fue retirado.

    A quien trabaja aquí no hay que readmitirlo, y a quien está suspendido se le
    reactiva. Llamar al endpoint en esos casos no puede colarse por la puerta de
    atrás y cambiarle el rol.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (await _crear(alpha_client, seeded, username="novaaqui")).json()

    activo = await alpha_client.post(
        f"/api/route/users/{creado['id']}/reenrollment",
        json={"role_id": seeded.alpha.roles["route_admin"]},
    )
    assert activo.status_code == 409
    assert activo.json()["detail"]["code"] == "same_tenant_active"

    await alpha_client.put(
        f"/api/route/users/{creado['id']}/access", json={"is_active": False}
    )
    suspendido = await alpha_client.post(
        f"/api/route/users/{creado['id']}/reenrollment",
        json={"role_id": seeded.alpha.roles["route_admin"]},
    )
    assert suspendido.status_code == 409
    assert suspendido.json()["detail"]["code"] == "same_tenant_inactive"

    # El rol no cambió por intentarlo.
    filas = await _pertenencias(seeded.alpha.id, creado["id"])
    assert filas[0]["role_id"] == seeded.alpha.roles["supervisor"]


async def test_a_stale_confirmation_does_not_overwrite_the_other_admin(
    seeded, alpha_client,
):
    """Casos borde 13 y 14: dos administradores, una sola readmisión.

    El `UPDATE` es condicional sobre la lápida, así que el segundo no encuentra
    nada que restaurar y responde 409 en lugar de pisar el rol que el primero
    acabó de aplicar. Es el mismo patrón que ya protege la terminalización de
    una parada: la condición viaja en el `WHERE`, no en un `if` previo.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "carrera")

    primera = await alpha_client.post(
        f"/api/route/users/{user_id}/reenrollment",
        json={"role_id": seeded.alpha.roles["route_admin"]},
    )
    assert primera.status_code == 200

    segunda = await alpha_client.post(
        f"/api/route/users/{user_id}/reenrollment",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["detail"]["code"] in (
        "reenrollment_already_done",
        "same_tenant_active",
    )

    filas = await _pertenencias(seeded.alpha.id, user_id)
    assert filas[0]["role_id"] == seeded.alpha.roles["route_admin"], (
        "el rol del primero sobrevive"
    )


async def test_two_simultaneous_re_enrollments_restore_once(seeded, alpha_client):
    """Caso borde 13, de verdad concurrente.

    Dos peticiones a la vez: una restaura y la otra se encuentra el trabajo
    hecho. Lo decide la base con su `WHERE`, no una comprobación previa que las
    dos pasarían.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "simultanea")

    cuerpo = {"role_id": seeded.alpha.roles["supervisor"]}
    a, b = await asyncio.gather(
        alpha_client.post(f"/api/route/users/{user_id}/reenrollment", json=cuerpo),
        alpha_client.post(f"/api/route/users/{user_id}/reenrollment", json=cuerpo),
        return_exceptions=True,
    )
    codigos = sorted(
        r.status_code for r in (a, b) if not isinstance(r, BaseException)
    )
    assert 200 in codigos, codigos
    assert codigos.count(200) == 1, f"sólo una puede restaurar: {codigos}"

    filas = await _pertenencias(seeded.alpha.id, user_id)
    assert len(filas) == 1


async def test_route_history_survives_the_round_trip(seeded, alpha_client):
    """Caso borde 7 y 8, y §14.22: el historial de Route no se toca.

    As-built, medido y no supuesto: retirar el acceso al tenant **no** pone
    lápida al perfil de supervisor ni a sus asignaciones. A01 eligió el borrado
    blando de la pertenencia justamente por eso — `supervisor_profile` la
    referencia con `CASCADE`, y un borrado físico se habría llevado por delante
    la designación de Route con su historial de vehículos.

    Así que aquí no hay nada que resucitar, y §13 se cumple sin hacer nada: ni
    retirar ni readmitir toca esas filas. Lo que se comprueba es exactamente
    eso, que siguen intactas antes y después del viaje de ida y vuelta.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (await _crear(alpha_client, seeded, username="conhistoria")).json()

    perfil = (
        await alpha_client.post("/api/supervisors", json={"user_id": creado["id"]})
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": "V-A03",
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    await alpha_client.delete(f"/api/route/users/{creado['id']}")
    await alpha_client.post(
        f"/api/route/users/{creado['id']}/reenrollment",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )

    async with async_session_maker() as session:
        asignaciones = await session.scalar(
            text(
                "SELECT count(*) FROM vehicle_assignment "
                "WHERE company_id = :c AND supervisor_profile_id = :p"
            ),
            {"c": seeded.alpha.id, "p": perfil["id"]},
        )
        perfil_vivo = await session.scalar(
            text(
                "SELECT deleted_at IS NULL FROM supervisor_profile WHERE id = :p"
            ),
            {"p": perfil["id"]},
        )
    assert asignaciones == 1, "el historial de vehículos sigue ahí"
    assert perfil_vivo is True, (
        "la designación nunca se retiró, así que sigue viva y nadie la resucitó"
    )


# ── Seguridad ───────────────────────────────────────────────────────────────


async def test_a_supervisor_cannot_re_enroll_anyone(seeded, alpha_client):
    """§12: el Supervisor sigue denegado, también en este endpoint nuevo.

    Exige `users.create`, la misma autoridad con la que se da acceso por primera
    vez. El Supervisor no la tiene, y readmitir no le abre una puerta lateral.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "prohibida")

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.post(
        f"/api/route/users/{user_id}/reenrollment",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )
    assert respuesta.status_code == 403, respuesta.text

    filas = await _pertenencias(seeded.alpha.id, user_id)
    assert filas[0]["deleted_at"] is not None, "sigue retirada"


async def test_re_enrollment_cannot_cross_tenants(seeded, alpha_client, beta_client):
    """§12 y L6: el tenant sale del contexto autenticado, nunca del cliente.

    Se retira a alguien en beta y se intenta readmitirlo desde alpha. La
    respuesta no confirma que exista: es la misma que para cualquier
    identificador desconocido.
    """
    await beta_client.login(seeded.beta.users["route_admin"].email)
    creado = (
        await beta_client.post(
            "/api/route/users",
            json={
                "username": "deotrotenant",
                "email": "deotrotenant@example.com",
                "first_name": "Otra",
                "last_name": "Persona",
                "password": BUENA,
                "gender": True,
                "role_id": seeded.beta.roles["supervisor"],
            },
        )
    ).json()
    await beta_client.delete(f"/api/route/users/{creado['id']}")

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        f"/api/route/users/{creado['id']}/reenrollment",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["detail"]["code"] == "username_unavailable"

    # Y la pertenencia de beta sigue retirada, sin que alpha la haya tocado.
    filas = await _pertenencias(seeded.beta.id, creado["id"])
    assert len(filas) == 1 and filas[0]["deleted_at"] is not None


async def test_the_platform_superuser_still_only_assigns_route_roles(
    seeded, alpha_client,
):
    """§15: el Superadmin en la superficie de Route no escapa a su acotación.

    La regla de A02 es doble —contexto de producto **o** rol de producto del
    actor— y el contexto de Route acota por sí solo. La identidad de plataforma
    no la relaja.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    user_id = await _retirar(alpha_client, seeded, "porsuperadmin")

    await alpha_client.login(seeded.platform_admin.email)
    respuesta = await alpha_client.post(
        f"/api/route/users/{user_id}/reenrollment",
        json={"role_id": seeded.alpha.roles["owner"]},
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_a_duplicate_create_is_consistent(seeded, alpha_client):
    """§13.12 y §15: dos envíos idénticos dan un resultado y un conflicto.

    El doble clic existe. El segundo envío no puede crear una segunda identidad
    ni una segunda pertenencia: encuentra a la persona que el primero acaba de
    crear y devuelve el conflicto que corresponde a su estado, que es activo.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    primero = await _crear(alpha_client, seeded, username="doblenvio")
    assert primero.status_code in (200, 201), primero.text

    segundo = await _crear(alpha_client, seeded, username="doblenvio")
    assert segundo.status_code == 409, segundo.text
    assert segundo.json()["detail"]["code"] == "same_tenant_active"

    async with async_session_maker() as session:
        identidades = await session.scalar(
            text('SELECT count(*) FROM "user" WHERE username = :n'),
            {"n": "doblenvio"},
        )
    assert identidades == 1, "una sola identidad"
    assert len(await _pertenencias(seeded.alpha.id, primero.json()["id"])) == 1


async def test_two_simultaneous_creates_produce_one_user(seeded, alpha_client):
    """El mismo caso, de verdad concurrente.

    La clasificación previa mejora el mensaje; no sustituye a la restricción.
    Dos peticiones a la vez pasan las dos la clasificación —el nombre está libre
    en ese instante— y es la base la que impide la segunda. Por eso la captura
    de `IntegrityError` sigue estando debajo.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    a, b = await asyncio.gather(
        _crear(alpha_client, seeded, username="carreracrear"),
        _crear(alpha_client, seeded, username="carreracrear"),
        return_exceptions=True,
    )
    codigos = sorted(
        r.status_code for r in (a, b) if not isinstance(r, BaseException)
    )
    assert sum(1 for c in codigos if c in (200, 201)) == 1, codigos

    async with async_session_maker() as session:
        identidades = await session.scalar(
            text('SELECT count(*) FROM "user" WHERE username = :n'),
            {"n": "carreracrear"},
        )
    assert identidades == 1, "la base impide la segunda, aunque ambas clasifiquen"
