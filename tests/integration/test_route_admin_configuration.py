"""
Configuración de CER Route operable desde el producto (cierre de RTE02).

El estándar de este cierre, literal: **ninguna tarea normal de administración
de RTE02 debe requerir Postman, llamadas directas a la API, edición directa de
la base ni intervención de un desarrollador.**

Lo que se prueba aquí es esa frase, traducida a comprobaciones:

* el Route Admin administra usuarios **con las capacidades del núcleo**, no con
  unas inventadas para Route;
* designar supervisor es una operación normal del producto, y no puede
  duplicarse ni cruzar tenants;
* las ocho listas se comportan igual — **parametrizado sobre las ocho**, porque
  probar una y suponer las otras siete es exactamente el error que el
  requisito prohíbe;
* el Route Admin no puede escalar a privilegio de plataforma por ninguna de
  las puertas nuevas.
"""

import pytest
from sqlalchemy import select, text

from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for
from app.database import async_session_maker
from app.routers_api.standardvalues.models import StandardValueList
from app.routers_api.users.models import Users
from tests.integration.conftest import TEST_PASSWORD


pytestmark = pytest.mark.integration


#: Las ocho listas aprobadas. Los tests de valores se parametrizan sobre esta
#: tupla para que ninguna quede sin cubrir.
TODAS_LAS_LISTAS = tuple(codigo.value for codigo in StandardValueList)


NUEVO_USUARIO = {
    "username": "nuevo_operador",
    "email": "nuevo.operador@alpha.example.com",
    "first_name": "Nuevo",
    "last_name": "Operador",
    "gender": False,
    "password": "UnaClaveSegura123!",
}


# ── Administración de usuarios con capacidades del núcleo ───────────────────


def test_route_admin_uses_core_user_capabilities_not_route_ones():
    """No existe una capacidad `route.users.*`: sería autorizar lo mismo dos veces."""
    plantilla = next(t for t in DEFAULT_ROLES if t.name == "route_admin")
    concedidas = set(capabilities_for(plantilla))

    assert {"users.read", "users.create", "users.update", "roles.read"} <= concedidas

    inventadas = {c for c in concedidas if c.startswith("route.users")}
    assert not inventadas, (
        f"El Route Admin no debe tener capacidades de usuario propias: {inventadas}"
    )


async def test_route_admin_can_create_a_tenant_user(seeded, alpha_client):
    """El alta completa —usuario, pertenencia y rol— en una sola operación."""
    acceso = await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert acceso.status_code == 200

    respuesta = await alpha_client.post(
        "/api/users",
        json={**NUEVO_USUARIO, "role_id": seeded.alpha.roles["supervisor"]},
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["email"] == NUEVO_USUARIO["email"]
    assert cuerpo["role_id"] == seeded.alpha.roles["supervisor"]
    assert cuerpo["is_active"] is True
    # Nunca se concede privilegio de plataforma por esta vía.
    assert cuerpo["is_superuser"] is False


async def test_the_created_user_belongs_only_to_the_acting_tenant(
    seeded, alpha_client, beta_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (
        await alpha_client.post(
            "/api/users",
            json={**NUEVO_USUARIO, "role_id": seeded.alpha.roles["viewer"]},
        )
    ).json()

    await beta_client.login(seeded.beta.users["route_admin"].email)
    listado = (await beta_client.get("/api/users/pagination?page_size=100")).json()

    ids_beta = {fila["id"] for fila in listado["results"]}
    assert creado["id"] not in ids_beta


async def test_route_admin_can_update_and_suspend_a_user(seeded, alpha_client):
    """Suspender es del ciclo de vida del núcleo; no hay borrado físico."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (
        await alpha_client.post(
            "/api/users",
            json={**NUEVO_USUARIO, "role_id": seeded.alpha.roles["viewer"]},
        )
    ).json()

    editado = await alpha_client.put(
        f"/api/users/{creado['id']}", json={"first_name": "Renombrado"}
    )
    assert editado.status_code == 200
    assert editado.json()["first_name"] == "Renombrado"

    suspendido = await alpha_client.put(
        f"/api/users/{creado['id']}/access", json={"is_active": False}
    )
    assert suspendido.status_code == 200
    assert suspendido.json()["is_active"] is False

    # Sigue existiendo: la identidad no se destruye al suspender el acceso.
    async with async_session_maker() as session:
        sigue = await session.scalar(
            select(Users).where(Users.id == creado["id"])
        )
    assert sigue is not None

    restaurado = await alpha_client.put(
        f"/api/users/{creado['id']}/access", json={"is_active": True}
    )
    assert restaurado.json()["is_active"] is True


async def test_a_supervisor_cannot_administer_users(seeded, alpha_client):
    """El rol de campo no administra identidad. Lo corta el servidor."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    assert (await alpha_client.get("/api/users/pagination")).status_code == 403
    assert (
        await alpha_client.post(
            "/api/users",
            json={**NUEVO_USUARIO, "role_id": seeded.alpha.roles["viewer"]},
        )
    ).status_code == 403


async def test_a_viewer_cannot_create_users(seeded, alpha_client):
    """`users.read` no alcanza para crear: son capacidades distintas."""
    await alpha_client.login(seeded.alpha.users["viewer"].email)

    assert (await alpha_client.get("/api/users/pagination")).status_code == 200
    assert (
        await alpha_client.post(
            "/api/users",
            json={**NUEVO_USUARIO, "role_id": seeded.alpha.roles["viewer"]},
        )
    ).status_code == 403


async def test_route_admin_cannot_grant_platform_superuser(seeded, alpha_client):
    """El contrato del núcleo ni siquiera acepta el campo: 422, no 200.

    Es el control que importa, porque no depende de que nadie recuerde
    filtrarlo: `is_superuser` no está en el schema de entrada (D6).
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.post(
        "/api/users",
        json={
            **NUEVO_USUARIO,
            "role_id": seeded.alpha.roles["viewer"],
            "is_superuser": True,
        },
    )
    assert respuesta.status_code == 422

    async with async_session_maker() as session:
        creado = await session.scalar(
            select(Users).where(Users.email == NUEVO_USUARIO["email"])
        )
    assert creado is None, "no debe haberse creado ningún usuario"


async def test_route_admin_cannot_escalate_an_existing_user_to_superuser(
    seeded, alpha_client,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.put(
        f"/api/users/{seeded.alpha.users['viewer'].id}",
        json={"is_superuser": True},
    )
    assert respuesta.status_code == 422

    async with async_session_maker() as session:
        sigue = await session.scalar(
            select(Users).where(Users.id == seeded.alpha.users["viewer"].id)
        )
    assert sigue.is_superuser is False


async def test_route_admin_cannot_administer_roles_themselves(seeded, alpha_client):
    """Puede asignar roles existentes; no fabricar uno con más capacidades."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    assert (await alpha_client.get("/api/roles")).status_code == 200
    assert (
        await alpha_client.post("/api/roles", json={"name": "inventado"})
    ).status_code == 403


# ── Designación de supervisor desde el producto ─────────────────────────────


async def test_the_candidates_screen_shows_the_whole_chain(seeded, alpha_client):
    """usuario -> designación -> vehículo, en una sola lectura."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.get("/api/supervisors/candidates")
    assert respuesta.status_code == 200

    filas = respuesta.json()
    por_usuario = {fila["user_id"]: fila for fila in filas}

    # Todos los usuarios del tenant aparecen, sean supervisores o no.
    assert seeded.alpha.users["viewer"].id in por_usuario
    sin_designar = por_usuario[seeded.alpha.users["viewer"].id]
    assert sin_designar["supervisor_profile_id"] is None
    assert sin_designar["current_vehicle"] is None
    assert sin_designar["role_name"] == "viewer"

    # Y no se cuelan los de la otra compañía.
    assert seeded.beta.users["viewer"].id not in por_usuario


async def test_a_tenant_user_can_be_designated_from_the_product(
    seeded, alpha_client,
):
    """La designación es una operación normal, no una llamada manual a la API."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    creado = await alpha_client.post(
        "/api/supervisors", json={"user_id": seeded.alpha.users["viewer"].id}
    )
    assert creado.status_code == 200

    filas = (await alpha_client.get("/api/supervisors/candidates")).json()
    fila = next(f for f in filas if f["user_id"] == seeded.alpha.users["viewer"].id)
    assert fila["supervisor_profile_id"] is not None
    assert fila["supervisor_active"] is True


async def test_a_duplicate_designation_is_rejected(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(
        "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
    )

    repetida = await alpha_client.post(
        "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
    )
    assert repetida.status_code == 409


async def test_a_designation_is_removed_by_deactivating_not_deleting(
    seeded, alpha_client,
):
    """Retirar conserva el perfil: la historia lo sigue referenciando."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()

    retirado = await alpha_client.put(
        f"/api/supervisors/{perfil['id']}",
        json={"is_active": False, "version": perfil["version"]},
    )
    assert retirado.status_code == 200
    assert retirado.json()["is_active"] is False

    # El perfil sigue existiendo, marcado como retirado.
    filas = (await alpha_client.get("/api/supervisors/candidates")).json()
    fila = next(
        f for f in filas if f["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["supervisor_profile_id"] == perfil["id"]
    assert fila["supervisor_active"] is False

    restaurado = await alpha_client.put(
        f"/api/supervisors/{perfil['id']}",
        json={"is_active": True, "version": retirado.json()["version"]},
    )
    assert restaurado.json()["is_active"] is True


async def test_a_supervisor_with_a_vehicle_cannot_be_undesignated(
    seeded, alpha_client,
):
    """Primero se cierra la asignación; si no, quedaría un vehículo huérfano."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "RAV4", "year": 2024, "unit": "V-900",
                "fuel_grade": "regular", "operational_mpg": "27.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )

    respuesta = await alpha_client.put(
        f"/api/supervisors/{perfil['id']}",
        json={"is_active": False, "version": perfil["version"]},
    )
    assert respuesta.status_code == 409


async def test_the_candidates_endpoint_requires_both_capabilities(
    seeded, alpha_client,
):
    """Lee identidad **y** dominio de Route, así que exige las dos capacidades."""
    # `viewer` tiene users.read pero no route.vehicles.read.
    await alpha_client.login(seeded.alpha.users["viewer"].email)
    assert (await alpha_client.get("/api/supervisors/candidates")).status_code == 403

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.get("/api/supervisors/candidates")).status_code == 200


# ── Las ocho listas, parametrizadas ─────────────────────────────────────────


@pytest.mark.parametrize("list_code", TODAS_LAS_LISTAS)
async def test_every_list_supports_the_full_value_lifecycle(
    seeded, alpha_client, list_code,
):
    """Crear, leer, editar, retirar y restaurar — en las **ocho** listas.

    Parametrizado a propósito: probar una lista y suponer que las otras siete
    están bien cableadas es justo lo que el requisito de cierre prohíbe.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    # Crear
    creado = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": list_code, "label": "Primer valor"},
    )
    assert creado.status_code == 200, creado.text
    valor = creado.json()
    assert valor["list_code"] == list_code

    # Leer
    activos = (await alpha_client.get(f"/api/standard-values/{list_code}")).json()
    assert [v["id"] for v in activos] == [valor["id"]]

    # Editar
    editado = await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"label": "Valor renombrado", "version": valor["version"]},
    )
    assert editado.status_code == 200
    assert editado.json()["label"] == "Valor renombrado"

    # Retirar
    retirado = await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"is_active": False, "version": editado.json()["version"]},
    )
    assert retirado.status_code == 200
    assert retirado.json()["is_active"] is False

    # Ya no se ofrece...
    assert (await alpha_client.get(f"/api/standard-values/{list_code}")).json() == []

    # ...pero sigue siendo resoluble para la historia.
    con_retirados = (
        await alpha_client.get(
            f"/api/standard-values/{list_code}?include_inactive=true"
        )
    ).json()
    assert [v["id"] for v in con_retirados] == [valor["id"]]

    # Restaurar
    restaurado = await alpha_client.put(
        f"/api/standard-values/{valor['id']}",
        json={"is_active": True, "version": retirado.json()["version"]},
    )
    assert restaurado.status_code == 200
    assert restaurado.json()["is_active"] is True


@pytest.mark.parametrize("list_code", TODAS_LAS_LISTAS)
async def test_every_list_supports_reordering(seeded, alpha_client, list_code):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    primero = (
        await alpha_client.post(
            "/api/standard-values", json={"list_code": list_code, "label": "A"}
        )
    ).json()
    segundo = (
        await alpha_client.post(
            "/api/standard-values", json={"list_code": list_code, "label": "B"}
        )
    ).json()

    reordenado = await alpha_client.post(
        f"/api/standard-values/{list_code}/reorder",
        json={"value_ids": [segundo["id"], primero["id"]]},
    )
    assert reordenado.status_code == 200
    assert [v["label"] for v in reordenado.json()] == ["B", "A"]


@pytest.mark.parametrize("list_code", TODAS_LAS_LISTAS)
async def test_every_list_is_tenant_scoped(
    seeded, alpha_client, beta_client, list_code,
):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    await alpha_client.post(
        "/api/standard-values",
        json={"list_code": list_code, "label": "Sólo de alpha"},
    )

    await beta_client.login(seeded.beta.users["route_admin"].email)
    etiquetas = {
        v["label"]
        for v in (await beta_client.get(f"/api/standard-values/{list_code}")).json()
    }
    assert "Sólo de alpha" not in etiquetas


async def test_the_eight_lists_are_exactly_the_approved_ones(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    listas = (await alpha_client.get("/api/standard-values/lists")).json()

    assert {fila["code"] for fila in listas} == set(TODAS_LAS_LISTAS)
    assert len(TODAS_LAS_LISTAS) == 8


# ── Auditoría del cierre ────────────────────────────────────────────────────


async def test_the_designation_lifecycle_is_audited(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users["supervisor"].id}
        )
    ).json()
    await alpha_client.put(
        f"/api/supervisors/{perfil['id']}",
        json={"is_active": False, "version": perfil["version"]},
    )

    async with async_session_maker() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT action, actor_user_id FROM audit_event WHERE "
                    "entity_type = 'supervisor_profile' AND entity_id = :id "
                    "ORDER BY id"
                ),
                {"id": perfil["id"]},
            )
        ).mappings().all()

    assert [fila["action"] for fila in filas] == ["create", "deactivate"]
    assert all(
        fila["actor_user_id"] == seeded.alpha.users["route_admin"].id
        for fila in filas
    )


async def test_user_administration_is_audited_by_core(seeded, alpha_client):
    """El núcleo ya audita identidad; no se crea un mecanismo paralelo.

    Si el núcleo no dejara traza, este test lo haría visible en vez de que la
    ausencia pasara desapercibida.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = (
        await alpha_client.post(
            "/api/users",
            json={**NUEVO_USUARIO, "role_id": seeded.alpha.roles["viewer"]},
        )
    ).json()

    async with async_session_maker() as session:
        total = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE entity_type = 'user' "
                    "AND entity_id = :id"
                ),
                {"id": creado["id"]},
            )
        ).scalar_one()

    assert total >= 1, (
        "El alta de usuario no dejó traza de auditoría. El núcleo debería "
        "registrarla; si no lo hace, es un hallazgo que hay que reportar, no "
        "algo que Route deba resolver con un mecanismo paralelo."
    )


# ── Quién puede leer las listas, y con qué alcance (RTE04-C5) ────────────────


async def test_a_supervisor_can_read_the_values_their_trip_requires(
    seeded, alpha_client,
):
    """Sin esto, tres contextos de viaje eran imposibles de arrancar.

    Employee Visit, Check Delivery y Office exigen un valor de lista **antes**
    de salir. El formulario del supervisor tiene que poder leer las opciones; si
    recibe 403, la regla obligatoria es imposible de satisfacer y el viaje no
    arranca nunca. Se descubrió validando el flujo en un navegador real: los
    tests de API no lo veían porque mandan el identificador directamente.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    creado = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "employee_visit_reasons", "label": "Payroll question"},
    )
    assert creado.status_code == 200

    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.get("/api/standard-values/employee_visit_reasons")

    assert respuesta.status_code == 200
    assert [v["label"] for v in respuesta.json()] == ["Payroll question"]


async def test_a_supervisor_cannot_see_retired_values(seeded, alpha_client):
    """Leer para elegir no es administrar.

    Un valor retirado no se puede volver a elegir, así que ofrecerlo en un
    formulario operativo sería enseñar una opción que el servidor rechazaría.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    respuesta = await alpha_client.get(
        "/api/standard-values/employee_visit_reasons?include_inactive=true"
    )

    assert respuesta.status_code == 403
    assert "route.standardvalues.manage" in respuesta.json()["detail"]


async def test_a_supervisor_still_cannot_change_the_lists(seeded, alpha_client):
    """El límite de privilegio: se concedió lectura, no administración."""
    await alpha_client.login(seeded.alpha.users["supervisor"].email)

    creacion = await alpha_client.post(
        "/api/standard-values",
        json={"list_code": "office_purposes", "label": "Invented by a supervisor"},
    )

    assert creacion.status_code == 403
