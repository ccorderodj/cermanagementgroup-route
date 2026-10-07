"""Del dato persistido a la pantalla: una sola cifra, contada una sola vez.

Qué defiende este archivo
--------------------------
Que el kilometraje oficial que vive en `TripMileage` llegue **igual** a Today /
Live y a Activity Explorer, y que ninguna unión de la consulta lo multiplique.

Son dos riesgos distintos y los dos tienen su test aquí:

* **la conversión** — que cada superficie convierta metros a millas con la misma
  regla. Hasta este delta había dos fórmulas en el repositorio, y no eran
  equivalentes;
* **la agregación** — que un viaje con varias actividades, o con varios tramos,
  siga aportando sus millas **una vez**.

Por qué 57 695 metros y no un número redondo
---------------------------------------------
Porque es el primer valor donde las dos fórmulas que convivían publican cifras
distintas:

    exacta       57695 / 1609.344        = 35.857...  -> 35.9
    aproximada   57695 * 0.000621371     = 35.849...  -> 35.8

57,7 km es una jornada corriente de campo, no un caso de laboratorio. Un test
con 20 000 m —12,4 por las dos vías— habría pasado en verde sin detectar nada,
que es exactamente lo que ocurrió hasta ahora.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.routers_api.mileage.read import METROS_POR_MILLA, millas_oficiales
from app.routers_api.mileage.routing import SegmentResult, set_road_router
from tests.integration.test_mileage_cross_surface import (
    _abrir_jornada,
    _calcular,
    _dia_de_la_jornada,
    _estado_de,
    _explorer,
    _live,
    _supervisor,
    _viaje_con_evidencia,
)

pytestmark = pytest.mark.integration

#: Donde las dos fórmulas discrepan. Ver el docstring del módulo.
METROS_DISCRIMINANTES = Decimal("57695")
MILLAS_EXACTAS = "35.9"
MILLAS_DE_LA_FORMULA_VIEJA = "35.8"


class RouterDeDistanciaFija:
    """Devuelve siempre la misma distancia por tramo."""

    name = "fijo"

    def __init__(self, metros: Decimal) -> None:
        self.metros = metros
        self.llamadas = 0

    async def distance(self, origen, destino) -> SegmentResult:
        self.llamadas += 1
        return SegmentResult(
            distance_meters=self.metros, provider="fijo", method="test", version="1"
        )


@pytest.fixture
def router_discriminante():
    """Un tramo de 57 695 m: 69 km/h en 50 minutos, dentro de lo plausible."""
    fijo = RouterDeDistanciaFija(METROS_DISCRIMINANTES)
    previo = set_road_router(fijo)
    try:
        yield fijo
    finally:
        set_road_router(previo)


# ── La regla de conversión, una sola ────────────────────────────────────────


def test_la_conversion_es_la_division_exacta():
    """La milla terrestre son 1609,344 m exactos. Se divide, no se multiplica.

    El inverso —0,000621371…— no tiene representación decimal finita, así que
    cualquier constante multiplicativa es una truncada. Este test fija la
    dirección de la operación, que es de donde venía la discrepancia.
    """
    assert METROS_POR_MILLA == Decimal("1609.344")
    assert millas_oficiales(METROS_DISCRIMINANTES) == Decimal(MILLAS_EXACTAS)

    aproximada = (METROS_DISCRIMINANTES * Decimal("0.000621371")).quantize(
        Decimal("0.1")
    )
    assert aproximada == Decimal(MILLAS_DE_LA_FORMULA_VIEJA), (
        "si esto falla, el ejemplo del docstring dejó de ser discriminante"
    )
    assert millas_oficiales(METROS_DISCRIMINANTES) != aproximada


def test_no_queda_ninguna_segunda_formula_en_el_codigo():
    """Lista cerrada: el multiplicador truncado no vuelve por la puerta de atrás.

    Es el mismo recurso que `tests/test_public_surface.py` usa con la superficie
    pública: lo que crece solo se detiene con una comprobación que obliga a
    editarla a mano y, al editarla, a justificarla.
    """
    sospechosas = [
        f"{ruta}:{n}"
        for ruta in pathlib.Path("app").rglob("*.py")
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        if "0.000621371" in linea and "read.py" not in str(ruta)
    ]
    assert not sospechosas, (
        "reapareció una segunda fórmula de conversión; la autoritativa es "
        f"`millas_oficiales` en app/routers_api/mileage/read.py: {sospechosas}"
    )


# ── MV-02 a MV-05: el dato persistido llega exacto a las dos superficies ────


async def test_las_dos_superficies_publican_la_cifra_exacta(
    seeded, alpha_client, router_discriminante
):
    """MV-02 a MV-05 sobre el valor que distingue las dos fórmulas.

    Antes de este delta las dos pantallas habrían publicado 35.8 y la API de
    kilometraje 35.9 para el mismo viaje. Ahora las tres dicen lo mismo.
    """
    await _supervisor(alpha_client, seeded, unidad="V-EXACTA")
    jornada = await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()

    estado, metros = await _estado_de(viaje["id"])
    assert estado == "calculated"
    assert metros == METROS_DISCRIMINANTES, metros

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s
        for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["official_miles"] == MILLAS_EXACTAS, (
        f"Today / Live publicó {fila['official_miles']}; con la fórmula vieja "
        f"habría publicado {MILLAS_DE_LA_FORMULA_VIEJA}"
    )

    vista = await _explorer(
        alpha_client,
        range="day",
        date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert vista["summary"]["official_miles"] == MILLAS_EXACTAS
    assert vista["activities"][0]["official_miles"] == MILLAS_EXACTAS


# ── MV-07: ninguna unión multiplica el kilometraje ──────────────────────────


async def test_varias_actividades_en_una_parada_no_multiplican_las_millas(
    seeded, alpha_client, router_discriminante
):
    """MV-07. El bloque de actividad admite **varias** actividades elegidas.

    Si alguna consulta uniera `activity_execution_activity`, un viaje con tres
    actividades aportaría sus millas tres veces. La unidad de `activity_execution`
    por viaje está garantizada por la base —`uq_activity_execution_trip`—, pero
    la tabla de actividades elegidas es uno-a-muchos y no la protege nada.
    """
    await _supervisor(alpha_client, seeded, unidad="V-MULTI")
    jornada = await _abrir_jornada(alpha_client, seeded)

    from app.routers_api.standardvalues.provisioning import provision_standard_values
    from app.database import async_session_maker

    async with async_session_maker() as session:
        await provision_standard_values(session, company_id=seeded.alpha.id)
        await session.commit()

    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": "ABC Manufacturing"},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})
    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})

    valores = (
        await alpha_client.get("/api/standard-values/client_visit_activities")
    ).json()
    elegidas = [v["id"] for v in valores[:3]]
    assert len(elegidas) >= 2, "el catálogo no trae suficientes actividades"

    inicio = await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/start",
        json={"activity_ids": elegidas},
    )
    assert inicio.status_code in (200, 201), inicio.text
    resultados = (await alpha_client.get("/api/standard-values/outcomes")).json()
    await alpha_client.post(
        f"/api/trips/{viaje['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultados[0]["id"]},
    )

    ahora = datetime.now(timezone.utc)
    for kind, (lat, lon), hace in (
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

    await _calcular()
    estado, metros = await _estado_de(viaje["id"])
    assert estado == "calculated"
    assert metros == METROS_DISCRIMINANTES

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s
        for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["official_miles"] == MILLAS_EXACTAS, (
        f"{len(elegidas)} actividades multiplicaron las millas en Today / Live: "
        f"{fila['official_miles']}"
    )

    vista = await _explorer(
        alpha_client,
        range="day",
        date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert vista["summary"]["official_miles"] == MILLAS_EXACTAS, (
        f"{len(elegidas)} actividades multiplicaron las millas en Activity: "
        f"{vista['summary']['official_miles']}"
    )
    assert len(vista["activities"]) == 1, "una parada se dibujó varias veces"


async def test_un_viaje_de_varios_tramos_suma_sus_tramos_y_se_cuenta_una_vez(
    seeded, alpha_client, router_discriminante
):
    """MV-07, el otro vector: los tramos son detalle de auditoría, no millas extra.

    Un cambio de plan parte el viaje en dos tramos. `total_meters` es la suma de
    los dos —ése es el hecho del viaje— y el día debe contarlo **una** vez, no
    una por tramo.
    """
    from app.database import async_session_maker
    from sqlalchemy import text

    await _supervisor(alpha_client, seeded, unidad="V-TRAMOS")
    jornada = await _abrir_jornada(alpha_client, seeded)

    viaje = (
        await alpha_client.post(
            "/api/trips",
            json={"purpose": "client_visit", "context_reference": "ABC Manufacturing"},
        )
    ).json()
    await alpha_client.post(f"/api/trips/{viaje['id']}/start", json={})

    ahora = datetime.now(timezone.utc)

    async def ubicar(kind, lat, lon, hace, subject_id=None):
        respuesta = await alpha_client.post(
            "/api/location/evidence",
            json={
                "event_kind": kind,
                "subject_id": subject_id or viaje["id"],
                "evidence_level": "fresh",
                "latitude": lat,
                "longitude": lon,
                "accuracy_m": "10.00",
                "device_captured_at": (ahora - timedelta(minutes=hace)).isoformat(),
            },
        )
        assert respuesta.status_code == 201, respuesta.text

    await ubicar("start_trip", 33.9500, -83.3800, 90)

    cambio = await alpha_client.post(
        f"/api/trips/{viaje['id']}/change-plan",
        json={"purpose": "client_visit", "context_reference": "XYZ Logistics"},
        headers={"Idempotency-Key": "cambio-de-plan-tramos"},
    )
    assert cambio.status_code == 200, cambio.text

    # El waypoint de un cambio de plan NO cuelga del viaje: cuelga de la fila
    # de `trip_purpose_change`. Es lo que permite que dos cambios del mismo
    # viaje tengan cada uno su punto, y no uno compartido.
    async with async_session_maker() as session:
        cambio_id = await session.scalar(
            text(
                "SELECT id FROM trip_purpose_change WHERE trip_id = :t "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"t": viaje["id"]},
        )
    assert cambio_id is not None, "el cambio de plan no dejó fila de historial"
    await ubicar("change_plan", 33.9700, -83.3500, 50, subject_id=cambio_id)

    await alpha_client.post(f"/api/trips/{viaje['id']}/arrive", json={})
    await ubicar("arrived", 33.9900, -83.3200, 10)

    await _calcular()
    estado, metros = await _estado_de(viaje["id"])
    assert estado == "calculated", estado

    async with async_session_maker() as session:
        tramos = await session.scalar(
            text(
                "SELECT count(*) FROM trip_mileage_segment s "
                "JOIN trip_mileage m ON m.id = s.trip_mileage_id "
                "WHERE m.trip_id = :t"
            ),
            {"t": viaje["id"]},
        )
    assert tramos == 2, f"se esperaban dos tramos, hay {tramos}"
    assert metros == METROS_DISCRIMINANTES * 2, metros

    esperado = str(millas_oficiales(METROS_DISCRIMINANTES * 2))
    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s
        for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["official_miles"] == esperado, (
        f"Today / Live publicó {fila['official_miles']} en vez de {esperado}: "
        "los tramos se contaron como viajes"
    )

    vista = await _explorer(
        alpha_client,
        range="day",
        date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert vista["summary"]["official_miles"] == esperado


# ── MV-08: calculado y pendiente conviven sin mentir ────────────────────────


async def test_calculado_y_pendiente_en_el_mismo_dia(
    seeded, alpha_client, router_discriminante
):
    """MV-08. Lo calculado se ve; lo pendiente se avisa y no suma cero.

    El viaje sin evidencia no puede enrutarse, así que queda pendiente. Lo que
    no puede pasar es que su ausencia se presente como un total final.
    """
    await _supervisor(alpha_client, seeded, unidad="V-MIXTO")
    jornada = await _abrir_jornada(alpha_client, seeded)

    await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    sin_evidencia = await _viaje_con_evidencia(
        alpha_client,
        company_id=seeded.alpha.id,
        referencia="XYZ Logistics",
        con_evidencia=False,
        con_actividad=False,
    )
    await _calcular()

    assert (await _estado_de(sin_evidencia["id"]))[0] == "pending_calculation"

    dia = await _dia_de_la_jornada(jornada["id"])
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    fila = next(
        s
        for s in (await _live(alpha_client))["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    )
    assert fila["official_miles"] == MILLAS_EXACTAS, (
        "el viaje calculado dejó de verse por culpa del pendiente"
    )
    assert fila["mileage_pending"] is True, (
        "no se avisó de que el total todavía no es final"
    )

    vista = await _explorer(
        alpha_client,
        range="day",
        date=dia.isoformat(),
        supervisor_user_id=seeded.alpha.users["supervisor"].id,
    )
    assert vista["summary"]["official_miles"] == MILLAS_EXACTAS
    assert vista["summary"]["mileage_pending"] is True
