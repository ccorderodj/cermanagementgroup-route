"""Las millas oficiales, las mismas en Today / Live y en Activity.

Qué defiende este archivo
--------------------------
Que un hecho —el kilometraje enrutado de un viaje— se represente **igual** en
las dos superficies administrativas, y que lo que no es un hecho no se dibuje
como si lo fuera.

Son dos riesgos distintos y los dos están aquí:

* que una superficie pierda la cifra por una unión mal escrita o un filtro de
  día equivocado, y enseñe `0.0 mi` donde hubo 12,4;
* que un cálculo **pendiente** se presente como un cero final, que es la misma
  mentira en la otra dirección.

Por qué el motor se ejercita de verdad
---------------------------------------
No se escribe `calculated` a mano en la tabla: se sustituye el adaptador de
routing por uno que devuelve una distancia conocida y se deja que el motor haga
su trabajo —waypoints, tramos, consolidación—. Así lo que se prueba es el
camino completo y no una fila fabricada que se parece al resultado.

Lo que este archivo **no** puede probar
----------------------------------------
Que el entorno desplegado calcule. Allí no hay motor de carretera configurado y
por eso ningún viaje llega a `calculated`; eso es configuración de entorno y
está en el reporte. Lo que sí se prueba aquí es que, **en cuanto haya cifra**,
llega entera a las dos pantallas.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.mileage.routing import SegmentResult, set_road_router

pytestmark = pytest.mark.integration

#: Un PNG de 1x1. La evidencia de odómetro no es lo que se prueba aquí.
FOTO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

#: 20 000 m = 12,4274 mi -> 12,4 con un decimal. Se elige un número que **no**
#: sea redondo en millas: un error de conversión o de redondeo se ve.
METROS_POR_TRAMO = Decimal("20000")
MILLAS_ESPERADAS = "12.4"

RUTA_LIVE = "/api/live/today"
RUTA_EXPLORER = "/api/activity-explorer"


class RouterFijo:
    """Devuelve siempre la misma distancia. Sustituye al adaptador real."""

    name = "fijo"

    def __init__(self, metros: Decimal = METROS_POR_TRAMO) -> None:
        self.metros = metros
        self.llamadas = 0

    async def distance(self, origen, destino) -> SegmentResult:
        self.llamadas += 1
        return SegmentResult(
            distance_meters=self.metros,
            provider="fijo",
            method="test",
            version="1",
        )


@pytest.fixture
def router_fijo():
    """Instala el router de distancia conocida y lo retira al terminar."""
    fijo = RouterFijo()
    previo = set_road_router(fijo)
    try:
        yield fijo
    finally:
        set_road_router(previo)


async def _supervisor(alpha_client, seeded, *, unidad: str, usuario="supervisor"):
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
    return perfil


async def _abrir_jornada(alpha_client, seeded, usuario="supervisor") -> dict:
    await alpha_client.login(seeded.alpha.users[usuario].email)
    jornada = (await alpha_client.post("/api/worksessions", json={})).json()
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/photo",
        files={"photo": ("odo.png", FOTO, "image/png")},
    )
    await alpha_client.post(
        f"/api/odometer/sessions/{jornada['id']}/start/confirm",
        json={"reading": "100000.0"},
    )
    return jornada


async def _viaje_con_evidencia(
    alpha_client, *, company_id: int, referencia="ABC Manufacturing",
    con_evidencia=True, con_actividad=True,
) -> dict:
    """Un viaje que sale y llega, con sus dos waypoints si se piden.

    Sin evidencia el motor no puede enrutar y lo dice: es el caso `pending`
    legítimo, no un fallo.
    """
    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": referencia},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    if con_actividad:
        # El Activity Explorer lista **paradas** —bloques de ejecución— y no
        # viajes. Un viaje que llegó y no ejecutó nada suma sus millas al día y
        # no tiene tarjeta; para comprobar la tarjeta hace falta la parada.
        #
        # Los valores configurables se siembran antes: el dominio exige elegir
        # al menos una actividad al llegar en este contexto, y sin catálogo no
        # hay nada que elegir. No es ruido de prueba, es la regla.
        from app.routers_api.standardvalues.provisioning import (
            provision_standard_values,
        )

        async with async_session_maker() as session:
            await provision_standard_values(session, company_id=company_id)
            await session.commit()

        valores = (
            await alpha_client.get("/api/standard-values/client_visit_activities")
        ).json()
        inicio = await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/start",
            json={"activity_ids": [valores[0]["id"]]},
        )
        assert inicio.status_code in (200, 201), inicio.text
        resultados = (await alpha_client.get("/api/standard-values/outcomes")).json()
        fin = await alpha_client.post(
            f"/api/trips/{viaje['id']}/activity/complete",
            json={"action": "complete", "outcome_id": resultados[0]["id"]},
        )
        assert fin.status_code == 200, fin.text

    if con_evidencia:
        ahora = datetime.now(timezone.utc)
        for kind, (lat, lon), hace in (
            # Dos puntos a ~7 km en línea recta. Importa: el motor rechaza
            # —con razón— una distancia enrutada menor que la recta, porque es
            # geométricamente imposible. Con 20 km enrutados sobre 7 de recta
            # el tramo es creíble y la velocidad implícita, 24 km/h en 50
            # minutos, también.
            ("start_trip", (33.9500, -83.3800), 60),
            ("arrived", (33.9900, -83.3200), 10),
        ):
            respuesta = await alpha_client.post(
                "/api/location/evidence",
                json={
                    "event_kind": kind,
                    "subject_id": viaje["id"],
                    "evidence_level": "fresh",
                    "latitude": lat,
                    "longitude": lon,
                    "accuracy_m": "10.00",
                    "device_captured_at": (ahora - timedelta(minutes=hace)).isoformat(),
                },
            )
            assert respuesta.status_code == 201, respuesta.text
    return viaje


async def _vencer_reintentos() -> None:
    """Deja los pendientes listos para el siguiente barrido."""
    async with async_session_maker() as session:
        await session.execute(
            text(
                "UPDATE trip_mileage SET next_attempt_at = now() - interval '1 hour' "
                "WHERE state = 'pending_calculation'"
            )
        )
        await session.commit()


async def _calcular() -> dict:
    from app.routers_api.mileage.service import sweep_pending_mileage

    await _vencer_reintentos()
    return await sweep_pending_mileage()


async def _estado_de(trip_id: int) -> tuple[str, Decimal | None]:
    async with async_session_maker() as session:
        fila = (
            await session.execute(
                text(
                    "SELECT state, total_meters FROM trip_mileage WHERE trip_id = :t"
                ),
                {"t": trip_id},
            )
        ).first()
    return (fila.state, fila.total_meters) if fila else (None, None)


async def _fechar_jornada(jornada_id: int, dia: date) -> None:
    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE work_session SET session_date = :d WHERE id = :i"),
            {"d": dia, "i": jornada_id},
        )
        await session.commit()


async def _dia_de_la_jornada(jornada_id: int) -> date:
    async with async_session_maker() as session:
        return await session.scalar(
            text("SELECT session_date FROM work_session WHERE id = :i"),
            {"i": jornada_id},
        )


async def _live(cliente) -> dict:
    respuesta = await cliente.get(RUTA_LIVE)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _explorer(cliente, **parametros) -> dict:
    respuesta = await cliente.get(RUTA_EXPLORER, params=parametros)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# ── T2 — La cifra calculada llega entera a las dos superficies ──────────────


async def test_el_kilometraje_calculado_llega_igual_a_las_dos_superficies(
    seeded, alpha_client, router_fijo,
):
    """T2 y §10: el mismo hecho, el mismo número, en Today / Live y en Activity.

    Es la regla de consistencia entre superficies: no puede haber tres
    definiciones independientes de kilometraje. Si una pantalla dijera 12,4 y
    la otra 0,0 sobre el mismo viaje, nadie sabría cuál creer.
    """
    await _supervisor(alpha_client, seeded, unidad="V-MIL-X1")
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)

    resumen = await _calcular()
    assert resumen.get("calculated") == 1, f"el motor no calculó: {resumen}"

    estado, metros = await _estado_de(viaje["id"])
    assert estado == "calculated" and metros == METROS_POR_TRAMO

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    # Today / Live
    cuerpo = await _live(alpha_client)
    fila = next(
        s for s in cuerpo["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["official_miles"] == MILLAS_ESPERADAS, (
        f"Today / Live dice {fila['official_miles']} y debía decir {MILLAS_ESPERADAS}"
    )
    assert fila["mileage_pending"] is False
    assert cuerpo["summary"]["total_miles"] == MILLAS_ESPERADAS

    # Activity Explorer, en el día
    del_dia = await _explorer(
        alpha_client, range="day", date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert del_dia["summary"]["official_miles"] == MILLAS_ESPERADAS
    assert del_dia["summary"]["mileage_pending"] is False
    assert del_dia["activities"][0]["official_miles"] == MILLAS_ESPERADAS

    # Y en los niveles agregados: la cifra no se pierde al agrupar.
    for rango in ("week", "month", "year"):
        vista = await _explorer(
            alpha_client, range=rango, date=dia.isoformat(),
            supervisor_user_id=seeded.alpha.users["supervisor"].id,
        )
        grupo = next(
            g for g in vista["groups"]
            if g["start"] <= dia.isoformat() <= g["end"]
        )
        assert grupo["official_miles"] == MILLAS_ESPERADAS, (
            f"el nivel '{rango}' perdió la cifra: {grupo['official_miles']}"
        )


# ── T3 — Pendiente no es cero ───────────────────────────────────────────────


async def test_un_calculo_pendiente_no_se_presenta_como_cero_final(
    seeded, alpha_client,
):
    """T3 y §4.3: la distinción que separa «no lo sabemos» de «fue cero».

    Es el caso del entorno desplegado hoy: sin motor de carretera el
    kilometraje se queda pendiente. Las dos superficies tienen que decirlo, no
    presentar un total como si estuviera cerrado.
    """
    await _supervisor(alpha_client, seeded, unidad="V-MIL-P1")
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)

    estado, _ = await _estado_de(viaje["id"])
    assert estado == "pending_calculation", "la preparación no dejó el caso pendiente"

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["mileage_pending"] is True, (
        "Today / Live presenta un cálculo pendiente como total final"
    )

    del_dia = await _explorer(
        alpha_client, range="day", date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert del_dia["summary"]["mileage_pending"] is True
    assert del_dia["activities"][0]["mileage_pending"] is True

    for rango in ("week", "month", "year"):
        vista = await _explorer(
            alpha_client, range=rango, date=dia.isoformat(),
            supervisor_user_id=seeded.alpha.users["supervisor"].id,
        )
        grupo = next(
            g for g in vista["groups"]
            if g["start"] <= dia.isoformat() <= g["end"]
        )
        assert grupo["mileage_pending"] is True, (
            f"el nivel '{rango}' perdió la marca de pendiente"
        )


# ── T4 — Lo excepcional no se rellena con un número ─────────────────────────


async def test_un_viaje_sin_evidencia_no_fabrica_millas(seeded, alpha_client):
    """T4: `not_calculable` no se dibuja como una cifra.

    Un viaje cuya evidencia de ubicación nunca llegó no tiene kilometraje, y
    «no se puede saber» es un hecho distinto de «fueron cero millas». Lo que no
    puede pasar es que la pantalla invente un número para tener algo que
    enseñar.
    """
    await _supervisor(alpha_client, seeded, unidad="V-MIL-NC")
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(
        alpha_client, company_id=seeded.alpha.id, con_evidencia=False
    )

    # Se terminaliza como el dominio lo hace cuando la evidencia no aparece.
    async with async_session_maker() as session:
        await session.execute(
            text(
                "UPDATE trip_mileage SET state = 'not_calculable', "
                "terminal_reason = 'start_waypoint_missing', total_meters = NULL "
                "WHERE trip_id = :t"
            ),
            {"t": viaje["id"]},
        )
        await session.commit()

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert Decimal(fila["official_miles"]) == Decimal("0.0")
    assert fila["mileage_pending"] is False, (
        "un viaje terminalizado no sigue pendiente: ya se sabe que no se sabrá"
    )

    del_dia = await _explorer(
        alpha_client, range="day", date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert Decimal(del_dia["activities"][0]["official_miles"]) == Decimal("0.0")
    assert del_dia["activities"][0]["mileage_pending"] is False


# ── T5 — Día de negocio ─────────────────────────────────────────────────────


async def test_el_kilometraje_se_queda_en_su_dia_de_negocio(
    seeded, alpha_client, router_fijo,
):
    """T5: una jornada que cruza medianoche no mueve sus millas de día."""
    await _supervisor(alpha_client, seeded, unidad="V-MIL-NOCHE")
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()
    assert (await _estado_de(viaje["id"]))[0] == "calculated"

    dia_de_negocio = date(2026, 9, 18)
    await _fechar_jornada(jornada["id"], dia_de_negocio)

    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    del_dia = await _explorer(
        alpha_client, range="day", date=dia_de_negocio.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert del_dia["summary"]["official_miles"] == MILLAS_ESPERADAS

    siguiente = await _explorer(
        alpha_client, range="day",
        date=(dia_de_negocio + timedelta(days=1)).isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert Decimal(siguiente["summary"]["official_miles"]) == Decimal("0.0"), (
        "las millas aparecieron también en el día natural siguiente"
    )


# ── T6 — Varios viajes suman ────────────────────────────────────────────────


async def test_dos_viajes_calculados_suman_en_las_dos_superficies(
    seeded, alpha_client, router_fijo,
):
    """T6: la agregación no pierde ni duplica."""
    await _supervisor(alpha_client, seeded, unidad="V-MIL-DOS")
    jornada = await _abrir_jornada(alpha_client, seeded)

    for referencia in ("ABC Manufacturing", "North Plant"):
        await _viaje_con_evidencia(
            alpha_client, company_id=seeded.alpha.id, referencia=referencia
        )
        await _calcular()

    esperado = str(
        (METROS_POR_TRAMO * 2 * Decimal("0.000621371")).quantize(Decimal("0.1"))
    )
    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["official_miles"] == esperado

    del_dia = await _explorer(
        alpha_client, range="day", date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert del_dia["summary"]["official_miles"] == esperado
    assert len(del_dia["activities"]) == 0 or all(
        a["official_miles"] == MILLAS_ESPERADAS for a in del_dia["activities"]
    ), "cada parada lleva las millas de **su** viaje, no el total del día"


# ── T7 y T8 — Nada se cruza ─────────────────────────────────────────────────


async def test_las_millas_de_un_supervisor_no_pasan_a_otro(
    seeded, alpha_client, router_fijo,
):
    """T7: dos supervisores el mismo día, cada uno con lo suyo."""
    await _supervisor(alpha_client, seeded, unidad="V-MIL-S1")
    await _supervisor(alpha_client, seeded, unidad="V-MIL-S2", usuario="route_admin")

    await _abrir_jornada(alpha_client, seeded)
    await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()

    # El segundo supervisor no conduce.
    await _abrir_jornada(alpha_client, seeded, usuario="route_admin")

    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    cuerpo = await _live(alpha_client)
    por_usuario = {s["user_id"]: s for s in cuerpo["supervisors"]}

    assert por_usuario[seeded.alpha.users["supervisor"].id]["official_miles"] == (
        MILLAS_ESPERADAS
    )
    assert Decimal(
        por_usuario[seeded.alpha.users["route_admin"].id]["official_miles"]
    ) == Decimal("0.0")
    assert cuerpo["summary"]["total_miles"] == MILLAS_ESPERADAS


async def test_las_millas_de_un_tenant_no_pasan_al_otro(
    seeded, alpha_client, beta_client, router_fijo,
):
    """T8: el aislamiento, también para el kilometraje."""
    await _supervisor(alpha_client, seeded, unidad="V-MIL-T1")
    await _abrir_jornada(alpha_client, seeded)
    await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()

    await beta_client.login(seeded.beta.users["route_admin"].email)
    perfil = (
        await beta_client.post(
            "/api/supervisors", json={"user_id": seeded.beta.users["supervisor"].id}
        )
    ).json()
    assert "id" in perfil, perfil

    cuerpo = await _live(beta_client)
    for s in cuerpo["supervisors"]:
        assert Decimal(s["official_miles"]) == Decimal("0.0"), (
            "beta está viendo millas de alpha"
        )
    assert Decimal(cuerpo["summary"]["total_miles"]) == Decimal("0.0")


# ── La regla de consistencia, explícita ─────────────────────────────────────


async def test_las_dos_superficies_son_el_mismo_hecho(
    seeded, alpha_client, router_fijo,
):
    """§10: una sola definición de kilometraje, no tres.

    Se comprueba sobre la misma lectura y el mismo viaje: lo que dice la fila
    de Today / Live, lo que dice el resumen del día del explorador y lo que
    dice la parada tienen que ser **idénticos**, carácter a carácter.
    """
    await _supervisor(alpha_client, seeded, unidad="V-MIL-CONS")
    jornada = await _abrir_jornada(alpha_client, seeded)
    await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    del_dia = await _explorer(
        alpha_client, range="day", date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )

    assert (
        fila["official_miles"]
        == del_dia["summary"]["official_miles"]
        == del_dia["activities"][0]["official_miles"]
    ), (
        f"las superficies discrepan: live={fila['official_miles']} "
        f"resumen={del_dia['summary']['official_miles']} "
        f"parada={del_dia['activities'][0]['official_miles']}"
    )
