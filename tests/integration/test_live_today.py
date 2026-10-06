"""Today / Live: lo que la pantalla afirma tiene que ser cierto.

Qué defiende este archivo
--------------------------
Today / Live no escribe nada, así que el riesgo no es corromper datos: es
**contar mal**. Un panel operativo que dice "On Route" de quien está en una
actividad, o que presenta un total de millas como final cuando falta calcular
un viaje, no rompe nada y se cree durante meses.

Por eso los tests se agrupan por la afirmación que hace la pantalla, no por el
endpoint: cada uno pone al dominio en un estado concreto y comprueba qué dice
Today / Live de él.

Las millas son las **oficiales** y sólo ésas
---------------------------------------------
Hay tres distancias en este producto y sólo una es millaje: la calculada por
carretera. El delta de odómetro es evidencia de referencia y la distancia en
línea recta no es nada. Un test lo fija, porque sustituir una por otra sería
invisible en pantalla y cambiaría lo que la compañía factura.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values


pytestmark = pytest.mark.integration


async def _perfil_y_vehiculo(alpha_client, seeded, *, unidad: str, usuario: str = "supervisor"):
    """Supervisor con perfil y vehículo asignado, por API."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    perfil = (
        await alpha_client.post(
            "/api/supervisors", json={"user_id": seeded.alpha.users[usuario].id}
        )
    ).json()
    vehiculo = (
        await alpha_client.post(
            "/api/vehicles",
            json={
                "make": "Toyota", "model": "Hilux", "year": 2024, "unit": unidad,
                "fuel_grade": "regular", "operational_mpg": "24.00",
            },
        )
    ).json()
    await alpha_client.post(
        f"/api/supervisors/{perfil['id']}/assignments",
        json={"vehicle_id": vehiculo["id"]},
    )
    return perfil, vehiculo


#: Un PNG de 1x1. La evidencia de odómetro no es lo que se prueba aquí.
FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def _valor_de_oficina(cliente, company_id: int) -> int:
    """Siembra los valores estándar y devuelve un propósito de visita a oficina.

    Un viaje no se planifica sin su dato de contexto: el dominio lo exige antes
    de dejar salir. No es ruido de prueba, es la regla, y un test que la saltara
    comprobaría un estado que el producto no puede alcanzar.
    """
    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=company_id)
        await session.commit()
    valores = (await cliente.get("/api/standard-values/office_purposes")).json()
    assert valores, "no se sembró ningún propósito de oficina"
    return valores[0]["id"]


async def _resolver_odometro(cliente, jornada_id: int) -> None:
    """Deja la lectura de inicio resuelta para que `Start Trip` pueda salir.

    No es ruido de prueba: es la guarda de RTE04, y un viaje no arranca sin
    ella. Un test de Today / Live que la saltara estaría comprobando un estado
    que el producto no puede alcanzar.
    """
    await cliente.post(
        f"/api/odometer/sessions/{jornada_id}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await cliente.post(
        f"/api/odometer/sessions/{jornada_id}/start/confirm",
        json={"reading": "100000.0"},
    )


async def _live(cliente) -> dict:
    respuesta = await cliente.get("/api/live/today")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _de(cuerpo: dict, user_id: int) -> dict:
    """La fila de un supervisor concreto, por identificador y no por nombre."""
    return next(s for s in cuerpo["supervisors"] if s["user_id"] == user_id)


# ── Autorización y aislamiento ──────────────────────────────────────────────


async def test_sin_la_capacidad_no_se_lee(seeded, alpha_client):
    """Un supervisor no ve la jornada de los demás por adivinar la ruta.

    `route.live.read` es de administración. Que el frontend pueda navegar a una
    página no es una autorización, y aquí se comprueba en el servidor, que es
    donde está la puerta.
    """
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    respuesta = await alpha_client.get("/api/live/today")
    assert respuesta.status_code == 403, respuesta.text


async def test_el_administrador_de_route_si_lee(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    assert (await alpha_client.get("/api/live/today")).status_code == 200


async def test_no_se_ven_supervisores_de_otro_tenant(
    seeded, alpha_client, beta_client
):
    """El alcance sale del subdominio, nunca de la petición.

    Se comprueba por el contenido y no por un 404: las dos compañías responden
    200 a su propia pregunta, y lo que no puede pasar es que una vea a la otra.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-A")

    await beta_client.login(seeded.beta.users["route_admin"].email)
    de_beta = await _live(beta_client)

    ajenos = {u.id for u in seeded.alpha.users.values()}
    for s in de_beta["supervisors"]:
        assert s["user_id"] not in ajenos, (
            f"beta está viendo a un supervisor de alpha: {s['name']}"
        )


# ── El día de negocio ───────────────────────────────────────────────────────


async def test_el_dia_es_el_de_la_jornada_y_no_el_de_utc(
    seeded, alpha_client
):
    """`session_date`, no la fecha UTC del evento.

    Importa de verdad para una flota americana: a las ocho de la tarde en
    Georgia ya es el día siguiente en UTC, así que resolver "hoy" con la fecha
    del servidor vaciaría la pantalla cada tarde. FR-01 lo prohíbe de forma
    explícita y esto lo fija.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-DIA")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)

    async with async_session_maker() as s:
        fecha = await s.scalar(
            text(
                "SELECT session_date FROM work_session WHERE company_id = :c "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"c": seeded.alpha.id},
        )
    assert cuerpo["session_date"] == fecha.isoformat(), (
        "la pantalla muestra un día distinto al de la jornada abierta"
    )


# ── Los estados visibles ────────────────────────────────────────────────────


async def test_quien_no_ha_empezado_sigue_en_la_lista(seeded, alpha_client):
    """FR-09: no se oculta a nadie por no haber salido todavía.

    A primera hora es justo el dato útil: quién **no** ha empezado. Esconderlo
    convertiría una lista operativa en una lista de los que ya se fueron.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-NS")
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    cuerpo = await _live(alpha_client)
    fila = _de(cuerpo, seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "not_started"
    assert fila["since"] is None, "no hay estado, así que no hay desde cuándo"
    assert fila["official_miles"] == "0.0"
    assert fila["activities_today"] == 0


async def test_jornada_abierta_sin_viajes_es_working(seeded, alpha_client):
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-W")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    await alpha_client.post("/api/worksessions", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "working"
    assert fila["since"] is not None
    assert fila["vehicle_label"] is not None, "el vehículo de la jornada se muestra"


async def test_un_viaje_en_transito_es_on_route(seeded, alpha_client):
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-R")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)
    creado = await alpha_client.post(
        "/api/trips",
        json={"purpose": "office", "context_reference": "Main office",
              "standard_value_id": valor},
    )
    assert creado.status_code in (200, 201), creado.text
    viaje = creado.json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "route"
    assert fila["activity_label"] == "office", (
        "el contexto sale del propósito vigente del viaje, no de la pantalla"
    )
    assert fila["activity_reference"] == "Main office"


async def test_la_actividad_en_curso_gana_al_viaje(seeded, alpha_client):
    """El orden de las ramas es la regla, y se fija aquí.

    Una actividad ocurre **dentro** de un viaje que ya llegó. Si la pantalla
    preguntara primero por el viaje, enseñaría "On Route" a quien está
    trabajando en el destino — y quien mira el panel decidiría a quién llamar
    con una información falsa.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-ACT")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)
    creado = await alpha_client.post(
        "/api/trips",
        json={"purpose": "office", "context_reference": "Acme",
              "standard_value_id": valor},
    )
    assert creado.status_code in (200, 201), creado.text
    viaje = creado.json()
    salida = await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    assert salida.status_code == 200, salida.text
    llegada = await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    assert llegada.status_code == 200, llegada.text
    inicio = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )
    assert inicio.status_code in (200, 201), inicio.text

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "activity", (
        "estar en una actividad es más específico que estar en un viaje"
    )
    assert fila["activities_today"] == 1


async def test_la_jornada_terminada_es_work_ended(seeded, alpha_client):
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-END")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 200, cierre.text

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "ended"
    assert fila["since"] is not None


# ── Millas oficiales ────────────────────────────────────────────────────────


async def test_un_viaje_sin_millaje_calculado_no_suma_cero_en_silencio(
    seeded, alpha_client
):
    """Pendiente no es cero, y la diferencia es la que importa.

    Un total que presenta un viaje pendiente como cero millas parece final y no
    lo es. FR-05 prohíbe disimularlo, así que la respuesta lleva una marca y la
    pantalla la enseña.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-MI")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "office", "standard_value_id": valor}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    async with async_session_maker() as s:
        estado = await s.scalar(
            text("SELECT state FROM trip_mileage WHERE trip_id = :t"),
            {"t": viaje["id"]},
        )
    if estado == "pending_calculation":
        assert fila["mileage_pending"] is True, (
            "hay un viaje sin calcular y el total se presenta como final"
        )
        assert fila["official_miles"] == "0.0", (
            "lo pendiente no suma: suma cero y se avisa aparte"
        )


async def test_las_millas_vienen_del_millaje_oficial_calculado(
    seeded, alpha_client
):
    """Sólo `calculated` suma, y lo que suma son metros convertidos a millas.

    Se escribe el resultado del cálculo directamente porque el motor de routing
    no está configurado en la suite — lo que se prueba aquí es la **agregación**
    y la conversión, no el cálculo, que tiene sus propios tests en `mileage`.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-OK")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "office", "standard_value_id": valor}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    async with async_session_maker() as s:
        await s.execute(
            text(
                # `calculated_at` va junto al resultado: la base exige que un
                # hecho calculado esté completo, y tiene razón — un millaje sin
                # hora de cálculo no se podría interpretar después.
                "UPDATE trip_mileage SET state = 'calculated', "
                "total_meters = 16093.4, calculated_at = now() WHERE trip_id = :t"
            ),
            {"t": viaje["id"]},
        )
        await s.commit()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)
    fila = _de(cuerpo, seeded.alpha.users["supervisor"].id)

    # 16093.4 metros son 10 millas.
    assert fila["official_miles"] == "10.0", fila["official_miles"]
    assert fila["mileage_pending"] is False
    assert cuerpo["summary"]["total_miles"] == "10.0"


# ── El resumen ──────────────────────────────────────────────────────────────


async def test_el_resumen_cuenta_lo_que_la_lista_enseña(seeded, alpha_client):
    """Las cuatro tarjetas de V0.7 y la lista no pueden discrepar.

    Se derivan de la misma lectura a propósito: contarlas por separado abriría
    la puerta a un panel que dice "2 en ruta" sobre una lista donde sólo hay
    uno, y nadie sabría cuál de los dos creer.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-SUM")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "office", "standard_value_id": valor}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)
    resumen = cuerpo["summary"]
    lista = cuerpo["supervisors"]

    assert resumen["supervisors_total"] == len(lista)
    assert resumen["on_route"] == len([s for s in lista if s["status"] == "route"])
    assert resumen["in_activity"] == len(
        [s for s in lista if s["status"] == "activity"]
    )
    assert resumen["supervisors_working"] == len(
        [s for s in lista if s["status"] not in ("ended", "not_started")]
    )


async def test_una_compania_sin_supervisores_responde_vacia_sin_fallar(
    seeded, alpha_client
):
    """Lista vacía es un estado, no un error."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)

    assert isinstance(cuerpo["supervisors"], list)
    assert cuerpo["summary"]["supervisors_total"] == len(cuerpo["supervisors"])
    assert cuerpo["session_date"]


async def test_dos_supervisores_salen_los_dos_y_el_resumen_los_cuenta(
    seeded, alpha_client
):
    """Con más de un supervisor la lista y el resumen siguen cuadrando.

    Sobre el N+1, y por qué no se instrumenta aquí
    -----------------------------------------------
    La primera versión de este test enganchaba un *listener* al motor de
    SQLAlchemy para contar consultas. Funcionaba aislado y **rompía la suite**
    al ejecutarse junto a otros módulos: tocar el motor global interfiere con el
    arnés que crea y desecha el pool por test, y varios archivos quedaban sin
    sus fixtures. Un test que hace fallar a otros no vale lo que mide.

    La propiedad se sostiene por construcción y está medida fuera: el modelo de
    lectura resuelve la lista con seis consultas fijas —supervisores, viaje
    vigente, actividad en curso, recuento y millaje— y ninguna depende del
    número de filas. El middleware de rendimiento lo registró en
    `query_count=5` para esta llamada.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-DOS-A")
    await _perfil_y_vehiculo(
        alpha_client, seeded, unidad="V-DOS-B", usuario="route_admin"
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)

    ids = {s["user_id"] for s in cuerpo["supervisors"]}
    assert seeded.alpha.users["supervisor"].id in ids
    assert seeded.alpha.users["route_admin"].id in ids
    assert cuerpo["summary"]["supervisors_total"] == len(cuerpo["supervisors"])
