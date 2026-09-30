"""El motor de kilometraje segmentado (RTE06-CP3).

Los casos de §37, y los tres que más fácil se falsean
------------------------------------------------------
M1–M3, C1–C8, R1–R5, H1–H3 y L1–L2 vienen de la instrucción. Tres merecen una
nota, porque un test escrito de la forma obvia los deja pasar:

* **C4 (Change Plan Missing).** Comprobar sólo que el estado es
  `not_calculable` no basta: alguien podría calcular `Start→Arrived` y descartar
  el número. Estos tests comprueban además que **no hay tramos escritos** y que
  el total es nulo. El atajo silencioso es lo que persigue §17.
* **C7 (texto del destino).** Se cambia el texto y se comprueba que la
  distancia es **idéntica**. Sin la igualdad exacta, el test pasaría aunque se
  estuviera geocodificando algo.
* **H2 (purgado).** Se borra `location_fix` de verdad dentro del test. Si los
  tramos no llevaran las coordenadas copiadas, el kilometraje quedaría sin
  sustento — y ése es el punto entero de §28.

El doble de routing
-------------------
La suite normal no toca la red (§40). `_RouterFijo` devuelve distancias
deterministas y cuenta las llamadas, que es lo que permite afirmar cuántos
tramos se enrutaron. Hay además un test marcado que mide OSRM de verdad y sólo
corre si `ROUTE_ROUTING_URL` está configurada.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.standardvalues.provisioning import provision_standard_values
from app.routers_api.mileage.routing import (
    Punto,
    RoutingUnavailable,
    SegmentResult,
    haversine_meters,
    set_road_router,
)
from app.routers_api.mileage.service import MileageService, sweep_pending_mileage

pytestmark = pytest.mark.integration


AHORA = datetime.now(timezone.utc)

#: Cuatro puntos reales, separados unos 1,2 km cada uno (bajando por Manhattan).
#:
#: Están cerca a propósito. La primera versión usaba Manhattan, Newark, Trenton
#: y Filadelfia —130 km en línea recta— con un doble que devolvía 10 km por
#: tramo, y la comprobación geométrica de plausibilidad lo rechazó: por
#: carretera no se puede ir menos que en línea recta. El motor tenía razón y el
#: test estaba mal. Con puntos próximos, la distancia fija del doble es
#: coherente y la plausibilidad sólo salta cuando el test quiere que salte.
P0 = ("40.712800", "-74.0060000")
P1 = ("40.722800", "-74.0100000")
P2 = ("40.732800", "-74.0140000")
P3 = ("40.742800", "-74.0180000")


class _RouterFijo:
    """Doble determinista: distancia fija por tramo, y cuenta las llamadas."""

    name = "fake"

    def __init__(self, metros: str = "10000.00") -> None:
        self.metros = Decimal(metros)
        self.llamadas: list[tuple[str, str]] = []

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        self.llamadas.append(
            (f"{origen.latitude},{origen.longitude}", f"{destino.latitude},{destino.longitude}")
        )
        return SegmentResult(
            distance_meters=self.metros,
            provider=self.name,
            method="driving",
            version="test-1",
        )


class _RouterQueFalla:
    """Falla siempre, de forma transitoria o permanente según se pida."""

    name = "fake-broken"

    def __init__(self, *, transient: bool) -> None:
        self.transient = transient
        self.llamadas = 0

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        self.llamadas += 1
        raise RoutingUnavailable("nope", transient=self.transient)


class _RouterQueSanaAlSegundoIntento:
    """Falla la primera vez y responde a partir de la segunda (caso R1)."""

    name = "fake-flaky"

    def __init__(self) -> None:
        self.llamadas = 0

    async def distance(self, origen: Punto, destino: Punto) -> SegmentResult:
        self.llamadas += 1
        if self.llamadas == 1:
            raise RoutingUnavailable("temporary", transient=True)
        return SegmentResult(
            distance_meters=Decimal("12345.00"),
            provider=self.name,
            method="driving",
        )


@pytest.fixture
def router_fijo():
    """Instala el doble y restaura el adaptador real al terminar."""
    doble = _RouterFijo()
    previo = set_road_router(doble)
    yield doble
    set_road_router(previo)


@pytest.fixture
def router_roto_transitorio():
    doble = _RouterQueFalla(transient=True)
    previo = set_road_router(doble)
    yield doble
    set_road_router(previo)


@pytest.fixture
def router_roto_permanente():
    doble = _RouterQueFalla(transient=False)
    previo = set_road_router(doble)
    yield doble
    set_road_router(previo)


# ── Montaje ─────────────────────────────────────────────────────────────────


async def _viaje(cliente, seeded, *, purpose: str = "other"):
    await cliente.login(seeded.alpha.users["supervisor"].email)
    jornada = (await cliente.post("/api/worksessions", json={})).json()
    assert "id" in jornada, jornada
    viaje = (
        await cliente.post(
            "/api/trips", json={"purpose": purpose, "context_reference": "Task"}
        )
    ).json()
    assert "id" in viaje, viaje
    inicio = await cliente.post(f"/api/trips/{viaje['id']}/start", json={})
    assert inicio.status_code in (200, 201), inicio.text
    return jornada, viaje


async def _cambiar_plan(
    cliente, trip_id: int, *, referencia: str, purpose: str = "other"
) -> int:
    """Un `Change Plan`, y devuelve el id del cambio, que es su waypoint."""
    respuesta = await cliente.post(
        f"/api/trips/{trip_id}/change-plan",
        json={"purpose": purpose, "context_reference": referencia},
    )
    assert respuesta.status_code in (200, 201), respuesta.text
    cambios = (await cliente.get(f"/api/trips/{trip_id}/plan-changes")).json()
    lista = cambios if isinstance(cambios, list) else cambios["results"]
    return lista[-1]["id"]


async def _llegar(cliente, trip_id: int) -> None:
    respuesta = await cliente.post(f"/api/trips/{trip_id}/arrive", json={})
    assert respuesta.status_code in (200, 201), respuesta.text


async def _punto(cliente, *, event_kind: str, subject_id: int, coord, hace=0):
    """Registra un punto capturado `hace` minutos.

    Hacia atrás, no hacia delante: el servidor rechaza una captura futura
    —una medición no puede ocurrir después de recibirse— y una secuencia de
    waypoints con horas futuras nunca habría entrado. Así que `start_trip` es
    la más antigua y `arrived` la más reciente, que es el orden real de un
    viaje.
    """
    lat, lon = coord
    respuesta = await cliente.post(
        "/api/location/evidence",
        json={
            "event_kind": event_kind,
            "subject_id": subject_id,
            "evidence_level": "fresh",
            "latitude": lat,
            "longitude": lon,
            "accuracy_m": "10.00",
            "device_captured_at": (AHORA - timedelta(minutes=hace)).isoformat(),
        },
    )
    assert respuesta.status_code == 201, respuesta.text


async def _missing(cliente, *, event_kind: str, subject_id: int):
    respuesta = await cliente.post(
        "/api/location/missing",
        json={
            "event_kind": event_kind,
            "subject_id": subject_id,
            "reason_code": "recovery_window_exhausted",
        },
    )
    assert respuesta.status_code == 201, respuesta.text


async def _valor(cliente, list_code: str, etiqueta: str) -> int:
    """El id de un valor configurado, por etiqueta. Los ids se siembran."""
    respuesta = await cliente.get(f"/api/standard-values/{list_code}")
    assert respuesta.status_code == 200, respuesta.text
    for v in respuesta.json():
        if v["label"] == etiqueta:
            return v["id"]
    raise AssertionError(f"no está '{etiqueta}' en {list_code}")


async def _km(company_id: int, trip_id: int) -> dict:
    async with async_session_maker() as sesion:
        fila = (
            await sesion.execute(
                text(
                    "SELECT id, state, total_meters, terminal_reason, attempt_count "
                    "FROM trip_mileage WHERE company_id = :c AND trip_id = :t"
                ),
                {"c": company_id, "t": trip_id},
            )
        ).first()
    assert fila is not None, "el viaje terminado tiene que tener fila de kilometraje"
    return dict(fila._mapping)


async def _tramos(company_id: int, mileage_id: int) -> list[dict]:
    async with async_session_maker() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT sequence, from_event_kind, to_event_kind, distance_meters, "
                "provider, method, provider_version, from_latitude, to_latitude, "
                "from_evidence_level, to_evidence_level, from_captured_at, "
                "haversine_meters, from_fix_id FROM trip_mileage_segment "
                "WHERE company_id = :c AND trip_mileage_id = :m ORDER BY sequence"
            ),
            {"c": company_id, "m": mileage_id},
        )
        return [dict(f._mapping) for f in filas]


# ── M1 a M3: sin Change Plan ────────────────────────────────────────────────


async def test_a_simple_trip_is_one_segment(seeded, alpha_client, router_fijo):
    """M1: Start Trip → Arrived, un tramo, `calculated`."""
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=180
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculated", km
    assert km["total_meters"] == Decimal("10000.00")
    assert km["terminal_reason"] is None

    tramos = await _tramos(seeded.alpha.id, km["id"])
    assert len(tramos) == 1
    assert tramos[0]["from_event_kind"] == "start_trip"
    assert tramos[0]["to_event_kind"] == "arrived"
    assert tramos[0]["provider"] == "fake"
    assert len(router_fijo.llamadas) == 1


@pytest.mark.parametrize(
    "falta,razon",
    [("start_trip", "start_waypoint_missing"), ("arrived", "arrival_waypoint_missing")],
    ids=["sin-salida", "sin-llegada"],
)
async def test_a_missing_endpoint_is_not_calculable(
    seeded, alpha_client, router_fijo, falta, razon
):
    """M2 y M3: sin uno de los extremos no se calcula, y se dice cuál faltaba.

    Y **no se enruta nada**: comprobar las llamadas del doble es lo que
    demuestra que no se intentó inventar el tramo con el punto que sí había.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    if falta != "start_trip":
        await _punto(
            alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0, hace=300
        )
    else:
        await _missing(alpha_client, event_kind="start_trip", subject_id=viaje["id"])

    await _llegar(alpha_client, viaje["id"])
    if falta != "arrived":
        await _punto(
            alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3,
            hace=180,
        )
    else:
        await _missing(alpha_client, event_kind="arrived", subject_id=viaje["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "not_calculable", km
    assert km["terminal_reason"] == razon
    assert km["total_meters"] is None
    assert await _tramos(seeded.alpha.id, km["id"]) == []
    assert router_fijo.llamadas == [], "no se enruta lo que no se puede enrutar"


# ── C1 a C8: con Change Plan ────────────────────────────────────────────────


async def test_one_change_plan_produces_two_summed_segments(
    seeded, alpha_client, router_fijo
):
    """C1: `Miles = route(P0,P1) + route(P1,P2)`, y **un solo viaje**."""
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )

    cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="Desvío")
    await _punto(
        alpha_client, event_kind="change_plan", subject_id=cambio, coord=P1, hace=240
    )

    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=120
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculated", km
    assert km["total_meters"] == Decimal("20000.00"), "dos tramos sumados"

    tramos = await _tramos(seeded.alpha.id, km["id"])
    assert [t["sequence"] for t in tramos] == [1, 2]
    assert [t["from_event_kind"] for t in tramos] == ["start_trip", "change_plan"]
    assert [t["to_event_kind"] for t in tramos] == ["change_plan", "arrived"]

    # Un viaje sigue siendo un viaje (§15.4): no se creó otro.
    async with async_session_maker() as sesion:
        viajes = await sesion.scalar(
            text("SELECT count(*) FROM trip WHERE company_id = :c"),
            {"c": seeded.alpha.id},
        )
    assert viajes == 1


async def test_two_change_plans_produce_three_ordered_segments(
    seeded, alpha_client, router_fijo
):
    """C2: `P0 → P1 → P2 → P3`, tres tramos en orden de ocurrencia.

    El orden se comprueba por las coordenadas que recibió el router, no por la
    secuencia guardada: así el test falla si la secuencia se numera bien pero se
    enruta en otro orden.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )

    primero = await _cambiar_plan(alpha_client, viaje["id"], referencia="Uno")
    await _punto(
        alpha_client, event_kind="change_plan", subject_id=primero, coord=P1, hace=240
    )
    segundo = await _cambiar_plan(alpha_client, viaje["id"], referencia="Dos")
    await _punto(
        alpha_client, event_kind="change_plan", subject_id=segundo, coord=P2, hace=180
    )

    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=60
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculated", km
    assert km["total_meters"] == Decimal("30000.00"), "tres tramos sumados"

    assert router_fijo.llamadas == [
        (f"{P0[0]},{P0[1]}", f"{P1[0]},{P1[1]}"),
        (f"{P1[0]},{P1[1]}", f"{P2[0]},{P2[1]}"),
        (f"{P2[0]},{P2[1]}", f"{P3[0]},{P3[1]}"),
    ], "el orden de enrutado es el de ocurrencia"


async def test_a_recovered_change_plan_waypoint_keeps_its_real_timestamp(
    seeded, alpha_client, router_fijo
):
    """C3: el waypoint recuperado se usa, con su hora y su procedencia reales.

    La hora que se guarda en el tramo es la de **captura**, no la de subida: un
    punto recuperado tres minutos después del evento sigue diciendo cuándo se
    midió (§11, §28).
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )

    cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="Recuperado")
    medido = AHORA - timedelta(minutes=239)  # entre la salida y la llegada
    respuesta = await alpha_client.post(
        "/api/location/evidence",
        json={
            "event_kind": "change_plan",
            "subject_id": cambio,
            "evidence_level": "recovered",
            "latitude": P1[0],
            "longitude": P1[1],
            "accuracy_m": "45.00",
            "device_captured_at": medido.isoformat(),
        },
    )
    assert respuesta.status_code == 201, respuesta.text

    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=120
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])
    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculated", km

    tramos = await _tramos(seeded.alpha.id, km["id"])
    assert tramos[0]["to_evidence_level"] == "recovered"
    assert abs((tramos[1]["from_captured_at"] - medido).total_seconds()) < 2


async def test_a_missing_change_plan_waypoint_is_not_calculable(
    seeded, alpha_client, router_fijo
):
    """C4: el waypoint del cambio falta → `Not Calculable`. Sin atajos.

    Lo que hace válido este test no es el estado: es que **no hay tramos** y el
    total es nulo. Un `Start→Arrived` calculado y descartado dejaría el estado
    correcto y habría violado §17 igualmente.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )

    cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="Perdido")
    await _missing(alpha_client, event_kind="change_plan", subject_id=cambio)

    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=120
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "not_calculable", km
    assert km["terminal_reason"] == "change_plan_waypoint_missing"
    assert km["total_meters"] is None
    assert await _tramos(seeded.alpha.id, km["id"]) == []
    assert router_fijo.llamadas == [], (
        "no se enrutó Start→Arrived: eso es el atajo que §17 prohíbe"
    )

    # Y el Change Plan **se conserva** en su historia (§17).
    async with async_session_maker() as sesion:
        cambios = await sesion.scalar(
            text("SELECT count(*) FROM trip_purpose_change WHERE company_id = :c"),
            {"c": seeded.alpha.id},
        )
    assert cambios == 1


async def test_a_waypoint_still_inside_the_recovery_window_stays_pending(
    seeded, alpha_client, router_fijo
):
    """Falta el punto pero no está dado por perdido: sigue **pendiente**.

    Es la distinción que más importa del motor: "todavía no" no es "nunca".
    Terminalizar aquí marcaría `not_calculable` viajes cuya evidencia estaba en
    camino, y §27 hace irreversible ese error.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="En ventana")
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=120
    )
    assert cambio  # el cambio existe y no tiene ni punto ni missing

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "pending_calculation", km
    assert km["attempt_count"] == 1, "gastó un intento y volverá"
    assert router_fijo.llamadas == []


async def test_the_destination_text_never_changes_the_routed_coordinates(
    seeded, alpha_client
):
    """C7: otro texto de destino, **la misma** distancia. No hay geocodificación.

    Se corren dos viajes idénticos salvo el texto y se comparan los totales.
    Sin exigir igualdad exacta, el test pasaría aunque se geocodificara algo.
    """
    totales = []
    for referencia in ("Cliente del norte", "Un sitio completamente distinto"):
        doble = _RouterFijo()
        previo = set_road_router(doble)
        try:
            _, viaje = await _viaje(alpha_client, seeded)
            await _punto(
                alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0
            )
            cambio = await _cambiar_plan(
                alpha_client, viaje["id"], referencia=referencia
            )
            await _punto(
                alpha_client, event_kind="change_plan", subject_id=cambio, coord=P1,
                hace=240,
            )
            await _llegar(alpha_client, viaje["id"])
            await _punto(
                alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3,
                hace=120,
            )
            km = await _km(seeded.alpha.id, viaje["id"])
            await MileageService.calculate(mileage_id=km["id"])
            km = await _km(seeded.alpha.id, viaje["id"])
            assert km["state"] == "calculated", km
            totales.append((km["total_meters"], tuple(doble.llamadas)))
        finally:
            set_road_router(previo)
        # Cerrar la jornada para poder abrir otra en la segunda vuelta.
        async with async_session_maker() as sesion:
            await sesion.execute(
                text(
                    "UPDATE work_session SET status = 'ended', ended_at = now() "
                    "WHERE company_id = :c AND status = 'active'"
                ),
                {"c": seeded.alpha.id},
            )
            await sesion.commit()

    assert totales[0][0] == totales[1][0], "el texto no puede cambiar la distancia"
    assert totales[0][1] == totales[1][1], "ni las coordenadas enrutadas"


async def test_home_follows_the_same_segmented_rule(seeded, alpha_client, router_fijo):
    """C8 y L1: HOME usa la misma secuencia y cierra en `Arrived` (§18).

    El viaje empieza como otro contexto y **cambia a HOME** por el camino, que
    es el caso C8 tal como lo escribe la instrucción ("Change Plan then HOME").
    Al revés no funciona ni debería: un viaje que salió hacia casa y cambió de
    plan a `other` ya no va a casa, así que llegar no lo cierra. La primera
    versión de este test lo hacía al revés y esperaba `closed`; el producto
    tenía razón.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    cambio = await _cambiar_plan(
        alpha_client, viaje["id"], referencia="A casa", purpose="home"
    )
    await _punto(
        alpha_client, event_kind="change_plan", subject_id=cambio, coord=P1, hace=270
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P2, hace=210
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])
    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculated", km
    assert len(await _tramos(seeded.alpha.id, km["id"])) == 2

    # HOME cierra el viaje, y no crea bloque de actividad.
    async with async_session_maker() as sesion:
        estado = await sesion.scalar(
            text("SELECT status FROM trip WHERE id = :i"), {"i": viaje["id"]}
        )
        bloques = await sesion.scalar(
            text("SELECT count(*) FROM activity_execution WHERE company_id = :c"),
            {"c": seeded.alpha.id},
        )
    assert estado == "closed"
    assert bloques == 0


# ── L2: interrumpido ────────────────────────────────────────────────────────


async def test_an_interrupted_trip_fabricates_no_arrival(
    seeded, alpha_client, router_fijo
):
    """L2: sin llegada no se inventa endpoint, y el terminal lo dice (§19).

    Ni `End Work` como destino, ni el último punto conocido, ni nada. Y tampoco
    se crea un Missing de `Arrived`: ese evento no ocurrió.
    """
    jornada, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )

    # `end_anyway` es la confirmación explícita de D-07: el supervisor ve que
    # sigue en ruta y decide terminar igual. Es el único camino del producto a
    # un viaje `INTERRUPTED`, y por eso el test pasa por él en vez de escribir
    # el estado a mano.
    fin = await alpha_client.post(
        f"/api/worksessions/{jornada['id']}/end", json={"end_anyway": True}
    )
    assert fin.status_code in (200, 201), fin.text

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "not_calculable", km
    assert km["terminal_reason"] == "interrupted_without_arrival"
    assert km["total_meters"] is None
    assert router_fijo.llamadas == []

    async with async_session_maker() as sesion:
        perdidos = await sesion.scalar(
            text(
                "SELECT count(*) FROM missing_location_event "
                "WHERE company_id = :c AND event_kind = 'arrived'"
            ),
            {"c": seeded.alpha.id},
        )
    assert perdidos == 0, "no se crea Missing para un Arrived que nunca ocurrió"


# ── R1 a R5: routing y estados terminales ───────────────────────────────────


async def test_a_transient_provider_failure_retries_and_then_calculates(
    seeded, alpha_client
):
    """R1: Pending → reintento → Calculated. El primer fallo no terminaliza."""
    doble = _RouterQueSanaAlSegundoIntento()
    previo = set_road_router(doble)
    try:
        _, viaje = await _viaje(alpha_client, seeded)
        await _punto(
            alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0, hace=300
        )
        await _llegar(alpha_client, viaje["id"])
        await _punto(
            alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3,
            hace=180,
        )

        km = await _km(seeded.alpha.id, viaje["id"])
        await MileageService.calculate(mileage_id=km["id"])
        intermedio = await _km(seeded.alpha.id, viaje["id"])
        assert intermedio["state"] == "pending_calculation", intermedio
        assert intermedio["attempt_count"] == 1

        await MileageService.calculate(mileage_id=km["id"])
        final = await _km(seeded.alpha.id, viaje["id"])
        assert final["state"] == "calculated", final
        assert final["total_meters"] == Decimal("12345.00")
    finally:
        set_road_router(previo)


async def test_a_permanent_provider_failure_is_calculation_failed(
    seeded, alpha_client, router_roto_permanente
):
    """R2: la evidencia está, el proveedor no puede → `Calculation Failed`.

    Es distinto de `Not Calculable`, y la diferencia es la que §24 define: aquí
    los waypoints existen. Confundirlos diría que faltaba evidencia cuando no
    faltaba.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=180
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculation_failed", km
    assert km["terminal_reason"] == "routing_exhausted"
    assert km["total_meters"] is None, "un fallo no publica total"


async def test_bounded_retry_ends_in_a_terminal_state(
    seeded, alpha_client, router_roto_transitorio
):
    """R3: el reintento es acotado. Ningún viaje queda Pending para siempre.

    Se llama al cálculo tantas veces como permita la política y se comprueba
    que acaba terminal. Sin el límite, este bucle no terminaría nunca — que es
    exactamente lo que §24 prohíbe.
    """
    from app.core.platform.config_service import platform_config

    maximo = int(platform_config.policy("route_mileage")["max_attempts"])

    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=180
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    for _ in range(maximo + 1):
        await MileageService.calculate(mileage_id=km["id"])

    final = await _km(seeded.alpha.id, viaje["id"])
    assert final["state"] == "calculation_failed", final
    assert final["attempt_count"] <= maximo


async def test_the_sweeper_moves_stale_pending_forward(
    seeded, alpha_client, router_fijo
):
    """R3: el sweeper encuentra lo vencido y lo resuelve.

    Sin él, un viaje cuya primera pasada falló dependería de que alguien
    volviera a pedirlo.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=180
    )

    resumen = await sweep_pending_mileage()
    assert resumen["examined"] >= 1, resumen
    assert resumen.get("calculated", 0) >= 1, resumen

    km = await _km(seeded.alpha.id, viaje["id"])
    assert km["state"] == "calculated", km


async def test_an_implausible_segment_is_not_consolidated(seeded, alpha_client):
    """R4 y §26: un tramo increíble no se consolida.

    El doble devuelve una distancia menor que la línea recta, que es
    geométricamente imposible. No se guarda, y el viaje sigue pendiente hasta
    agotar la contingencia.
    """
    recta = haversine_meters(
        Punto(Decimal(P0[0]), Decimal(P0[1])), Punto(Decimal(P3[0]), Decimal(P3[1]))
    )
    doble = _RouterFijo(metros=str(recta / 2))
    previo = set_road_router(doble)
    try:
        _, viaje = await _viaje(alpha_client, seeded)
        await _punto(
            alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0, hace=300
        )
        await _llegar(alpha_client, viaje["id"])
        await _punto(
            alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3,
            hace=180,
        )

        km = await _km(seeded.alpha.id, viaje["id"])
        await MileageService.calculate(mileage_id=km["id"])

        km = await _km(seeded.alpha.id, viaje["id"])
        assert km["state"] == "pending_calculation", km
        assert "impossible" in (km["terminal_reason"] or "") or km["attempt_count"] == 1
        assert await _tramos(seeded.alpha.id, km["id"]) == [], (
            "un tramo sospechoso no se guarda"
        )
    finally:
        set_road_router(previo)


async def test_one_failing_segment_publishes_no_partial_total(seeded, alpha_client):
    """R5: si un tramo falla, no se publica la suma de los que sí salieron.

    El doble responde al primer tramo y falla en el segundo. §25 lo dice
    explícitamente: no se publica un total parcial como kilometraje final.
    """

    class _FallaElSegundo:
        name = "fake-second-fails"

        def __init__(self) -> None:
            self.llamadas = 0

        async def distance(self, origen, destino):
            self.llamadas += 1
            if self.llamadas == 1:
                return SegmentResult(
                    distance_meters=Decimal("5000.00"),
                    provider=self.name,
                    method="driving",
                )
            raise RoutingUnavailable("second leg down", transient=False)

    previo = set_road_router(_FallaElSegundo())
    try:
        _, viaje = await _viaje(alpha_client, seeded)
        await _punto(
            alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0, hace=300
        )
        cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="Medio")
        await _punto(
            alpha_client, event_kind="change_plan", subject_id=cambio, coord=P1,
            hace=240,
        )
        await _llegar(alpha_client, viaje["id"])
        await _punto(
            alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3,
            hace=120,
        )

        km = await _km(seeded.alpha.id, viaje["id"])
        await MileageService.calculate(mileage_id=km["id"])

        km = await _km(seeded.alpha.id, viaje["id"])
        assert km["state"] == "calculation_failed", km
        assert km["total_meters"] is None, "5000 m no se publica como total"
        assert await _tramos(seeded.alpha.id, km["id"]) == [], (
            "ni se guarda el tramo que sí salió: o el viaje entero o nada"
        )
    finally:
        set_road_router(previo)


# ── H1 a H3: integridad histórica ───────────────────────────────────────────


async def test_calculated_mileage_is_immutable(seeded, alpha_client):
    """H1: ni otro proveedor, ni otro umbral, ni un trabajo repetido lo cambian.

    Se calcula con un doble, se cambia el doble por otro que daría el doble de
    distancia, y se vuelve a llamar. El número no se mueve.
    """
    primero = _RouterFijo(metros="10000.00")
    previo = set_road_router(primero)
    try:
        _, viaje = await _viaje(alpha_client, seeded)
        await _punto(
            alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0, hace=300
        )
        await _llegar(alpha_client, viaje["id"])
        await _punto(
            alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3,
            hace=180,
        )
        km = await _km(seeded.alpha.id, viaje["id"])
        await MileageService.calculate(mileage_id=km["id"])
        calculado = await _km(seeded.alpha.id, viaje["id"])
        assert calculado["state"] == "calculated"
        assert calculado["total_meters"] == Decimal("10000.00")

        # Otro proveedor, otra distancia, y el trabajo repetido tres veces.
        set_road_router(_RouterFijo(metros="99999.00"))
        for _ in range(3):
            await MileageService.calculate(mileage_id=km["id"])

        despues = await _km(seeded.alpha.id, viaje["id"])
        assert despues["total_meters"] == Decimal("10000.00"), "no se recalcula"
        assert len(await _tramos(seeded.alpha.id, km["id"])) == 1, (
            "ni se duplica la provenance"
        )
    finally:
        set_road_router(previo)


async def test_provenance_survives_a_raw_fix_purge(seeded, alpha_client, router_fijo):
    """H2: se borra la evidencia cruda y el kilometraje sigue explicándose.

    Es el punto entero de §28. Si los tramos sólo guardaran `location_fix_id`,
    este test dejaría el número sin sustento — auditable hoy, inauditable
    mañana.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="Medio")
    await _punto(
        alpha_client, event_kind="change_plan", subject_id=cambio, coord=P1, hace=240
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=120
    )

    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])
    antes = await _tramos(seeded.alpha.id, km["id"])
    assert len(antes) == 2

    # El purgado. La tabla es append-only, así que hay que desactivar el
    # disparador: es lo mismo que hará el proceso de retención el día que
    # exista, y aquí se simula para comprobar que el kilometraje aguanta.
    async with async_session_maker() as sesion:
        await sesion.execute(text("ALTER TABLE location_fix DISABLE TRIGGER USER"))
        await sesion.execute(
            text("DELETE FROM location_fix WHERE company_id = :c"),
            {"c": seeded.alpha.id},
        )
        await sesion.execute(text("ALTER TABLE location_fix ENABLE TRIGGER USER"))
        await sesion.commit()

    despues = await _km(seeded.alpha.id, viaje["id"])
    assert despues["state"] == "calculated"
    assert despues["total_meters"] == Decimal("20000.00")

    tramos = await _tramos(seeded.alpha.id, km["id"])
    assert len(tramos) == 2, "los tramos siguen ahí"
    for tramo in tramos:
        # Todo lo que §28 exige poder auditar, sin la evidencia cruda.
        assert tramo["from_latitude"] is not None
        assert tramo["to_latitude"] is not None
        assert tramo["from_evidence_level"] in ("fresh", "degraded_cached", "recovered")
        assert tramo["from_captured_at"] is not None
        assert tramo["provider"] == "fake"
        assert tramo["method"] == "driving"
        assert tramo["provider_version"] == "test-1"
        assert tramo["distance_meters"] == Decimal("10000.00")


async def test_the_odometer_is_independent_of_routed_mileage(
    seeded, alpha_client, router_fijo
):
    """H3: el odómetro dice otra cosa y el kilometraje oficial no se mueve.

    Son dos fuentes de evidencia distintas (§20, §27). Que discrepen es normal
    y no es una señal para corregir ninguna de las dos.
    """
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=180
    )
    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    resultado = await _km(seeded.alpha.id, viaje["id"])
    assert resultado["total_meters"] == Decimal("10000.00")

    # La independencia se mide por el acoplamiento, no contando filas: una
    # primera versión de este test afirmaba que no había evidencia de odómetro,
    # y era falso —la jornada crea la suya—. Lo que importa es que escribir
    # odómetro no mueve el kilometraje.
    async with async_session_maker() as sesion:
        await sesion.execute(
            text(
                "UPDATE odometer_evidence "
                "SET confirmed_reading = COALESCE(confirmed_reading, 0) + 500 "
                "WHERE company_id = :c"
            ),
            {"c": seeded.alpha.id},
        )
        await sesion.commit()

    assert (await _km(seeded.alpha.id, viaje["id"]))["total_meters"] == Decimal(
        "10000.00"
    ), "el odómetro no es kilometraje oficial (§20) y no lo toca"

    # Y ninguna de las dos tablas referencia a la otra.
    async with async_session_maker() as sesion:
        cruces = await sesion.scalar(
            text(
                "SELECT count(*) FROM information_schema.table_constraints tc "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "  AND ((tc.table_name = 'trip_mileage' "
                "        AND ccu.table_name LIKE 'odometer%') "
                "    OR (tc.table_name LIKE 'odometer%' "
                "        AND ccu.table_name = 'trip_mileage'))"
            )
        )
    assert cruces == 0, "las dos evidencias no se referencian"


# ── L6: aislamiento ─────────────────────────────────────────────────────────


async def test_mileage_is_not_readable_across_tenants(
    seeded, alpha_client, beta_client, router_fijo
):
    """L6: el kilometraje de otro tenant no se lee ni se confirma que exista."""
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=180
    )
    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    propio = await alpha_client.get(f"/api/mileage/trips/{viaje['id']}")
    assert propio.status_code == 200, propio.text
    assert propio.json()["state"] == "calculated"
    assert propio.json()["total_miles"] is not None

    await beta_client.login(seeded.beta.users["supervisor"].email)
    ajeno = await beta_client.get(f"/api/mileage/trips/{viaje['id']}")
    assert ajeno.status_code == 404, ajeno.text


# ── §33: el contrato de lectura de la jornada ───────────────────────────────


async def test_the_session_total_declares_what_is_unresolved(
    seeded, alpha_client, router_fijo
):
    """§33: la suma del día no se presenta como si todo estuviera resuelto.

    Dos viajes: uno calculado y uno no calculable. La suma existe, y al lado el
    recuento de lo que no está resuelto y `fully_resolved` en falso.
    """
    jornada, primero = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=primero["id"], coord=P0,
        hace=300,
    )
    await _llegar(alpha_client, primero["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=primero["id"], coord=P3,
        hace=180,
    )

    # Un viaje `ARRIVED` sigue vivo, así que `POST /api/trips` devolvería **ese**
    # mismo viaje. Para tener dos hay que cerrar el primero, y lo que lo cierra
    # es terminar el trabajo de la parada — nada se cierra solo. La primera
    # versión de este test creaba el segundo sin cerrar el primero y acababa
    # operando dos veces sobre el mismo.
    async with async_session_maker() as sesion:
        await provision_standard_values(sesion, company_id=seeded.alpha.id)
        await sesion.commit()
    actividad = await _valor(alpha_client, "other_activities", "Housing Visit")
    bloque = await alpha_client.post(
        f"/api/trips/{primero['id']}/activity/start",
        json={"activity_ids": [actividad]},
    )
    assert bloque.status_code in (200, 201), bloque.text
    resultado = await _valor(alpha_client, "outcomes", "Completed")
    cierre = await alpha_client.post(
        f"/api/trips/{primero['id']}/activity/complete",
        json={"action": "complete", "outcome_id": resultado},
    )
    assert cierre.status_code in (200, 201), cierre.text

    segundo = (
        await alpha_client.post(
            "/api/trips", json={"purpose": "other", "context_reference": "Segundo"}
        )
    ).json()
    assert segundo["id"] != primero["id"], segundo
    await alpha_client.post(f"/api/trips/{segundo['id']}/start", json={})
    await _missing(alpha_client, event_kind="start_trip", subject_id=segundo["id"])
    await _llegar(alpha_client, segundo["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=segundo["id"], coord=P2,
        hace=60,
    )

    for viaje in (primero, segundo):
        km = await _km(seeded.alpha.id, viaje["id"])
        await MileageService.calculate(mileage_id=km["id"])

    respuesta = await alpha_client.get(f"/api/mileage/work-sessions/{jornada['id']}")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["calculated_trips"] == 1
    assert cuerpo["not_calculable_trips"] == 1
    assert cuerpo["fully_resolved"] is False, (
        "una suma parcial no puede parecer el total del día"
    )
    assert Decimal(cuerpo["calculated_miles"]) > 0


async def test_the_segment_provenance_endpoint_returns_the_audit_trail(
    seeded, alpha_client, router_fijo
):
    """§23: la provenance ordenada se puede leer, con todo lo que exige auditar."""
    _, viaje = await _viaje(alpha_client, seeded)
    await _punto(
        alpha_client, event_kind="start_trip", subject_id=viaje["id"], coord=P0,
        hace=300,
    )
    cambio = await _cambiar_plan(alpha_client, viaje["id"], referencia="Medio")
    await _punto(
        alpha_client, event_kind="change_plan", subject_id=cambio, coord=P1, hace=240
    )
    await _llegar(alpha_client, viaje["id"])
    await _punto(
        alpha_client, event_kind="arrived", subject_id=viaje["id"], coord=P3, hace=120
    )
    km = await _km(seeded.alpha.id, viaje["id"])
    await MileageService.calculate(mileage_id=km["id"])

    respuesta = await alpha_client.get(f"/api/mileage/trips/{viaje['id']}/segments")
    assert respuesta.status_code == 200, respuesta.text
    tramos = respuesta.json()
    assert [t["sequence"] for t in tramos] == [1, 2]
    for tramo in tramos:
        for campo in (
            "from_event_kind", "from_latitude", "from_evidence_level",
            "from_captured_at", "to_event_kind", "to_latitude",
            "to_evidence_level", "to_captured_at", "distance_meters",
            "distance_miles", "provider", "method", "computed_at",
        ):
            assert tramo[campo] is not None, campo


# ── V-3: la medición real, cuando hay motor ─────────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("ROUTE_ROUTING_URL"),
    reason="sin ROUTE_ROUTING_URL no hay motor real que medir (V-3)",
)
async def test_the_real_osrm_engine_returns_a_credible_road_distance():
    """V-3: medición contra OSRM de verdad, no contra un doble.

    La suite normal **no** depende de esto (§40): está marcado y sólo corre si
    hay motor configurado. Existe porque un doble no es evidencia suficiente de
    una integración productiva.

    La aserción es de orden de magnitud a propósito: la distancia por carretera
    Manhattan–Filadelfia depende de los datos OSM del extracto, y fijar un
    número exacto haría fallar el test al actualizar el mapa. Lo que se
    comprueba es que hay ruta, que es mayor que la línea recta y que está en el
    rango creíble — que es además lo que detecta el error de orden de
    coordenadas, porque longitud/latitud invertidas dan una distancia absurda.
    """
    from app.routers_api.mileage.routing import OsrmRouter

    motor = OsrmRouter(os.environ["ROUTE_ROUTING_URL"], timeout=20.0)
    origen = Punto(Decimal(P0[0]), Decimal(P0[1]))
    destino = Punto(Decimal(P3[0]), Decimal(P3[1]))

    resultado = await motor.distance(origen, destino)
    recta = haversine_meters(origen, destino)

    assert resultado.provider == "osrm"
    assert resultado.distance_meters > recta, "por carretera nunca es menos que la recta"
    assert Decimal("120000") < resultado.distance_meters < Decimal("250000"), (
        f"{resultado.distance_meters} m no es creíble para Manhattan-Filadelfia"
    )
