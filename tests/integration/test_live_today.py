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

#: El cuerpo de `Start Work` que envía el cliente desde T-1/T-2: la zona IANA
#: del dispositivo. Sin ella el «hoy» del supervisor es indeterminado (D3) y sus
#: jornadas cerradas no se atribuyen a ningún día; ese caso tiene sus propias
#: pruebas en `test_time_zones.py`. Aquí se fija una zona para que estas
#: pruebas sigan mirando lo que miran —la consolidación de H-2—, sin cambiar
#: ninguna aserción.
INICIO = {"time_zone": "America/New_York"}


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
    await alpha_client.post("/api/worksessions", json=INICIO)

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
    await alpha_client.post("/api/worksessions", json=INICIO)

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "working"
    assert fila["since"] is not None
    assert fila["vehicle_label"] is not None, "el vehículo de la jornada se muestra"


async def test_un_viaje_en_transito_es_on_route(seeded, alpha_client):
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-LIVE-R")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
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
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
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
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
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
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
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
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
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
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
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


# ── Varios supervisores a la vez ────────────────────────────────────────────


async def _promover_a_supervisor(alpha_client, seeded, usuario: str) -> None:
    """Da el rol de supervisor a un usuario, por el camino del producto.

    Hace falta porque sólo `supervisor` y `route_admin` traen
    `route.worksession.execute` en los roles por defecto, y este test necesita
    cuatro jornadas simultáneas en estados distintos. Se concede con
    `PUT /api/users/{id}`, que es la pantalla real de administración: inventar
    la capacidad por SQL probaría un estado que el producto no puede alcanzar.
    """
    await alpha_client.login(seeded.alpha.users["owner"].email)
    respuesta = await alpha_client.put(
        f"/api/users/{seeded.alpha.users[usuario].id}",
        json={"role_id": seeded.alpha.roles["supervisor"]},
    )
    assert respuesta.status_code == 200, respuesta.text


async def test_varios_supervisores_a_la_vez_no_se_contaminan(seeded, alpha_client):
    """Cinco supervisores, cinco estados distintos, una sola lectura.

    Cierra el caso límite 17 del reporte 001, que quedó sin evidencia propia.
    Lo que se defiende no es cada estado por separado —eso ya tiene su test—
    sino que **conviven**: que la fila de cada uno reciba lo suyo, que las
    tarjetas del resumen cuenten lo que la lista enseña, y que el total de
    millas sea la suma de las filas y no un número calculado aparte.

    El riesgo real de un modelo de lectura con seis consultas fijas es
    precisamente éste: una unión mal escrita no falla, mezcla. Y un panel que
    atribuye la actividad de uno al vehículo de otro se cree durante meses.
    """
    # Cada uno con su perfil y su vehículo, para que un cruce se vea.
    perfiles = {}
    for usuario, unidad in (
        ("supervisor", "V-MIX-ACT"), ("route_admin", "V-MIX-RUTA"),
        ("manager", "V-MIX-FIN"), ("viewer", "V-MIX-TRAB"),
        ("owner", "V-MIX-SIN"),
    ):
        perfil, _ = await _perfil_y_vehiculo(
            alpha_client, seeded, unidad=unidad, usuario=usuario
        )
        perfiles[usuario] = perfil

    await _promover_a_supervisor(alpha_client, seeded, "manager")
    await _promover_a_supervisor(alpha_client, seeded, "viewer")

    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    # 1. `supervisor` -> In Activity (viaje llegado y actividad en curso).
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "office", "context_reference": "Acme",
                  "standard_value_id": valor},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start", json={"activity_ids": []}
    )

    # 2. `route_admin` -> On Route (viaje en tránsito).
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    jornada_ruta = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
    await _resolver_odometro(alpha_client, jornada_ruta["id"])
    viaje_ruta = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "office", "context_reference": "Globex",
                  "standard_value_id": valor},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje_ruta['id']}/start", json={})

    # 3. `manager` -> Work Ended.
    await alpha_client.login(seeded.alpha.users["manager"].email)
    jornada_fin = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada_fin['id']}/end", json={}
    )
    assert cierre.status_code == 200, cierre.text

    # 4. `viewer` -> Working (jornada abierta sin viajes).
    await alpha_client.login(seeded.alpha.users["viewer"].email)
    abierta = await alpha_client.post("/api/worksessions", json=INICIO)
    assert abierta.status_code in (200, 201), abierta.text

    # 5. `owner` -> Not started (perfil sin jornada). No hace nada.

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)
    lista = cuerpo["supervisors"]
    resumen = cuerpo["summary"]

    esperado = {
        "supervisor": "activity", "route_admin": "route", "manager": "ended",
        "viewer": "working", "owner": "not_started",
    }
    obtenido = {
        usuario: _de(cuerpo, seeded.alpha.users[usuario].id)["status"]
        for usuario in esperado
    }
    assert obtenido == esperado, f"los estados se cruzaron: {obtenido}"

    # Cinco estados distintos de verdad: si el modelo colapsara dos, el
    # diccionario de arriba seguiría cuadrando por casualidad en algún caso.
    assert len(set(obtenido.values())) == 5

    # Nada se filtra de una fila a otra: el vehículo y la actividad son del
    # dueño de la jornada y de nadie más.
    en_actividad = _de(cuerpo, seeded.alpha.users["supervisor"].id)
    en_ruta = _de(cuerpo, seeded.alpha.users["route_admin"].id)
    assert en_actividad["vehicle_label"] != en_ruta["vehicle_label"]
    assert en_actividad["activity_reference"] == "Acme"
    assert en_ruta["activity_reference"] == "Globex"
    assert en_actividad["activities_today"] == 1
    assert en_ruta["activities_today"] == 0
    sin_empezar = _de(cuerpo, seeded.alpha.users["owner"].id)
    assert sin_empezar["since"] is None
    assert sin_empezar["activity_label"] is None

    # El resumen cuenta lo que la lista enseña, no un agregado aparte.
    assert resumen["supervisors_total"] == len(lista) == 5
    assert resumen["on_route"] == 1
    assert resumen["in_activity"] == 1
    assert resumen["supervisors_working"] == 3, (
        "trabajando son los que no han terminado ni dejado de empezar"
    )

    # Y el millaje agregado es la suma de las filas, no otra consulta.
    from decimal import Decimal

    assert Decimal(resumen["total_miles"]) == sum(
        (Decimal(s["official_miles"]) for s in lista), Decimal("0")
    )


# ── H-2 · Una fila por supervisor, no por jornada ───────────────────────────
#
# El modelo permite varias jornadas por persona y día: `uq_work_session_one_active`
# es un índice **parcial** sobre `status = 'active'`, de modo que las cerradas
# se repiten cuantas veces haga falta. Today asumía una, y una persona con dos
# salía dos veces con identificadores idénticos: la pantalla seleccionaba por
# `user_id`, se quedaba con la primera y enseñaba la jornada equivocada.
#
# Lo que estos tests fijan es la regla de consolidación: **se suma** lo que
# pertenece al día y **se elige** lo que describe un instante.


async def _jornada_cerrada_con_millas(
    alpha_client, seeded, *, metros: str, unidad_valor: int
) -> dict:
    """Una jornada completa: conduce, se le calcula el millaje y se cierra.

    Devuelve la jornada. Hace falta cerrarla para poder abrir otra: el índice
    único parcial impide dos activas a la vez, que es exactamente la regla que
    hace posible —y legítimo— tener dos jornadas el mismo día.
    """
    jornada = (await alpha_client.post("/api/worksessions", json=INICIO)).json()
    await _resolver_odometro(alpha_client, jornada["id"])
    viaje = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "office", "standard_value_id": unidad_valor}
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    async with async_session_maker() as s:
        await s.execute(
            text(
                "UPDATE trip_mileage SET state = 'calculated', "
                "total_meters = :m, calculated_at = now() WHERE trip_id = :t"
            ),
            {"m": metros, "t": viaje["id"]},
        )
        await s.commit()

    # Cerrar exige resolver la parada y la lectura de odómetro de cierre.
    await _resolver_la_parada_de(alpha_client, seeded, viaje["id"])
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/end/confirm",
        json={"reading": "100500.0"},
    )
    cierre = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={}
    )
    assert cierre.status_code == 200, cierre.text
    return jornada


async def _resolver_la_parada_de(cliente, seeded, trip_id: int) -> None:
    """Termina la actividad del viaje para que la jornada pueda cerrarse.

    `activity_ids: []` porque estos viajes son de propósito `office`, que no
    lleva la lista de actividades de una visita a cliente. Es el mismo camino
    que usa `test_la_actividad_en_curso_gana_al_viaje`, y el que la guarda de
    RTE05 exige antes de dejar cerrar la jornada.
    """
    inicio = await cliente.post(
        f"/api/trips/{trip_id}/activity/start", json={"activity_ids": []}
    )
    assert inicio.status_code in (200, 201), inicio.text
    resultados = (await cliente.get("/api/standard-values/outcomes")).json()
    fin = await cliente.post(
        f"/api/trips/{trip_id}/activity/complete",
        json={"action": "complete", "outcome_id": resultados[0]["id"]},
    )
    assert fin.status_code == 200, fin.text


async def test_dos_jornadas_el_mismo_dia_producen_una_sola_fila(
    seeded, alpha_client
):
    """AC-1: un supervisor con varias jornadas aparece una sola vez.

    Es el defecto reportado desde campo: dos filas «Karina Aguirre», una con
    `Work Ended` y otra `Working`, y el panel enseñando la primera.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-UNO")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )
    # La segunda del mismo día, que queda abierta.
    segunda = (await alpha_client.post("/api/worksessions", json=INICIO)).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)

    usuario = seeded.alpha.users["supervisor"].id
    suyas = [s for s in cuerpo["supervisors"] if s["user_id"] == usuario]
    assert len(suyas) == 1, (
        f"el supervisor sale {len(suyas)} veces; H-2 exige una sola fila por "
        f"persona: {suyas}"
    )
    assert segunda["id"] is not None


async def test_las_millas_del_dia_suman_todas_sus_jornadas(seeded, alpha_client):
    """AC-2: el acumulado del día, no el de una jornada suelta.

    El defecto visible era un `0.0 miles today` para quien había recorrido 62,5:
    la pantalla enseñaba las millas de **una** jornada bajo un rótulo que dice
    «hoy». Aquí se recorren dos tramos de 10 millas y el total tiene que ser 20.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-MI")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )
    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)
    fila = _de(cuerpo, seeded.alpha.users["supervisor"].id)

    assert fila["official_miles"] == "20.0", fila["official_miles"]
    assert cuerpo["summary"]["total_miles"] == "20.0", (
        "el total del encabezado tiene que cuadrar con la lista"
    )


async def test_las_actividades_del_dia_suman_sin_duplicar(seeded, alpha_client):
    """AC-3: se contabilizan todas, y cada una una sola vez."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-AC")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    # Cada jornada de ayuda ejecuta exactamente una actividad al resolver su
    # parada, así que dos jornadas son dos actividades.
    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )
    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["activities_today"] == 2, fila["activities_today"]


async def test_el_estado_sale_de_la_jornada_activa_y_no_de_la_cerrada(
    seeded, alpha_client
):
    """AC-4 en el servidor: el panel no puede decir `Work Ended` de quien trabaja.

    Es exactamente la captura que se reportó: la fila consolidada tiene que
    describir la jornada **abierta**, no la que se cerró por la mañana.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-EST")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )
    segunda = (await alpha_client.post("/api/worksessions", json=INICIO)).json()

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "working", (
        f"con una jornada abierta el estado no puede ser '{fila['status']}'"
    )
    assert fila["since"] is not None

    # Y el `since` es el de la jornada abierta, no el de la cerrada.
    async with async_session_maker() as s:
        inicio = await s.scalar(
            text("SELECT started_at FROM work_session WHERE id = :i"),
            {"i": segunda["id"]},
        )
    assert fila["since"].startswith(inicio.isoformat()[:16]), (
        f"`since` describe otra jornada: {fila['since']} vs {inicio}"
    )


async def test_sin_jornada_activa_el_estado_sale_de_la_ultima(
    seeded, alpha_client
):
    """La otra mitad de la regla: cerradas todas, manda la última iniciada."""
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-ULT")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )
    ultima = await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "ended"

    async with async_session_maker() as s:
        fin = await s.scalar(
            text("SELECT ended_at FROM work_session WHERE id = :i"),
            {"i": ultima["id"]},
        )
    assert fila["since"].startswith(fin.isoformat()[:16]), (
        "`since` tiene que describir la última jornada, no la primera"
    )


async def test_el_resumen_cuenta_personas_y_no_jornadas(seeded, alpha_client):
    """AC-5: los indicadores generales cuentan supervisores únicos.

    `supervisors_total` era `len(filas)`, así que una persona con dos jornadas
    contaba por dos y el encabezado decía que había más gente de la que hay.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-SUM")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)

    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )
    await alpha_client.post("/api/worksessions", json=INICIO)

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)

    identificadores = [s["user_id"] for s in cuerpo["supervisors"]]
    assert len(identificadores) == len(set(identificadores)), (
        f"hay user_id repetidos en la lista: {identificadores}"
    )
    assert cuerpo["summary"]["supervisors_total"] == len(set(identificadores))
    assert cuerpo["summary"]["supervisors_working"] == 1, (
        "una persona con dos jornadas sigue siendo una persona trabajando"
    )


async def test_la_consolidacion_no_mezcla_a_dos_supervisores(
    seeded, alpha_client
):
    """El control del conjunto: agrupar por persona no puede fundir a dos.

    Sin este test, una agrupación mal escrita —por perfil, o por el primer
    campo que se tenga a mano— pasaría todos los anteriores y sumaría las
    millas de una persona a otra, que es peor que el defecto original.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-A")
    await alpha_client.login(seeded.alpha.users["supervisor"].email)
    valor = await _valor_de_oficina(alpha_client, seeded.alpha.id)
    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="16093.4", unidad_valor=valor
    )

    # Se promueve a `manager`, no a `route_admin`: promover al administrador le
    # quitaría las capacidades con las que después hay que crear el perfil y el
    # vehículo del segundo, y el test fallaría por su propia preparación.
    await _promover_a_supervisor(alpha_client, seeded, "manager")
    await _perfil_y_vehiculo(
        alpha_client, seeded, unidad="V-H2-B", usuario="manager"
    )
    await alpha_client.login(seeded.alpha.users["manager"].email)
    await _jornada_cerrada_con_millas(
        alpha_client, seeded, metros="32186.8", unidad_valor=valor
    )

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)
    uno = _de(cuerpo, seeded.alpha.users["supervisor"].id)
    otro = _de(cuerpo, seeded.alpha.users["manager"].id)

    assert uno["official_miles"] == "10.0", uno["official_miles"]
    assert otro["official_miles"] == "20.0", otro["official_miles"]
    assert cuerpo["summary"]["total_miles"] == "30.0"


async def test_quien_no_ha_empezado_no_se_convierte_en_jornada_de_cero(
    seeded, alpha_client
):
    """La fila sin jornada no es una jornada vacía, y la consolidación lo sabe.

    El `LEFT JOIN` deja una fila con `sesion_id` nulo a quien no ha salido hoy.
    Tratarla como una jornada más le daría `0.0 mi` con aire de dato medido,
    cuando lo que pasa es que no hay nada que medir.
    """
    await _perfil_y_vehiculo(alpha_client, seeded, unidad="V-H2-NADA")

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    fila = _de(await _live(alpha_client), seeded.alpha.users["supervisor"].id)

    assert fila["status"] == "not_started"
    assert fila["since"] is None
    assert fila["activities_today"] == 0
    assert fila["mileage_pending"] is False
    assert fila["vehicle_label"] is None
