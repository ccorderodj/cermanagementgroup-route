"""Routing real: primario, reserva y la matriz de fallos (RTE06 cierre §5).

Por qué este archivo está separado y con puerta de entorno
-----------------------------------------------------------
§40 de la instrucción base prohíbe que la suite normal dependa de la red o de
un servicio pagado, y §13 del cierre permite que una prueba de integración viva
quede condicionada al entorno **siempre que la evidencia de cierre demuestre
que se ejecutó de verdad**. Así que estos tests se saltan sin motor configurado
y el reporte registra la ejecución con sus cifras.

Qué demuestra esto que un doble no puede
-----------------------------------------
Que el adaptador habla el protocolo real: el orden longitud/latitud de OSRM, el
`{lat, lon}` y los kilómetros de Valhalla, la forma de sus respuestas, sus
códigos de error. Un doble confirma la lógica del motor de kilometraje; sólo un
motor real confirma que el adaptador está bien escrito — y el modo de fallo más
peligroso del adaptador (coordenadas invertidas) devuelve distancias plausibles
de otro sitio, así que no rompe nada y miente.

Las coordenadas
---------------
Mónaco, porque es el extracto OSM de prueba del propio proyecto OSRM: pequeño,
estable y con calles reales. Los pares elegidos tienen ruta por carretera y una
relación conocida con la línea recta.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.routers_api.mileage.routing import (
    FallbackRouter,
    OsrmRouter,
    Punto,
    RoutingUnavailable,
    ValhallaRouter,
    haversine_meters,
)

pytestmark = pytest.mark.integration


PRIMARIO = os.environ.get("ROUTE_ROUTING_URL", "").strip()
RESERVA = os.environ.get("ROUTE_ROUTING_FALLBACK_URL", "").strip()

sin_primario = pytest.mark.skipif(
    not PRIMARIO, reason="sin ROUTE_ROUTING_URL no hay motor primario que medir"
)
sin_reserva = pytest.mark.skipif(
    not RESERVA,
    reason="sin ROUTE_ROUTING_FALLBACK_URL no hay motor de reserva que medir",
)

#: Puerto de Mónaco → barrio de Larvotto. Hay carretera y no es trivialmente
#: corta, así que una inversión de coordenadas se notaría.
A = Punto(Decimal("43.731100"), Decimal("7.419700"))
B = Punto(Decimal("43.739800"), Decimal("7.429800"))
#: Un tercer punto para el viaje de varios tramos.
C = Punto(Decimal("43.735500"), Decimal("7.424000"))


#: El radio con el que se mide, igual que en producción. Es el que convierte
#: "ajusta cualquier coordenada" en "no hay segmento".
RADIO = 1_000


def _router_primario() -> OsrmRouter:
    return OsrmRouter(PRIMARIO, timeout=20.0, snap_radius_m=RADIO)


def _router_reserva() -> ValhallaRouter:
    return ValhallaRouter(RESERVA, timeout=30.0)


# ── El primario, de verdad ──────────────────────────────────────────────────


@sin_primario
async def test_the_primary_engine_returns_a_credible_road_distance():
    """El motor primario responde y el adaptador interpreta bien la respuesta.

    La aserción es de relación, no de número exacto: la distancia vial depende
    de los datos OSM del extracto y fijar un valor haría fallar el test al
    actualizar el mapa. Lo que se comprueba es lo que un mapa nuevo no cambia:
    hay ruta, es **mayor** que la línea recta, y está en el mismo orden de
    magnitud. Eso es además lo que detecta el orden de coordenadas invertido,
    porque longitud/latitud al revés sitúa los puntos en el océano Índico y la
    distancia se vuelve absurda o no hay ruta.
    """
    resultado = await _router_primario().distance(A, B)
    recta = haversine_meters(A, B)

    assert resultado.provider == "osrm"
    assert resultado.method == "driving"
    assert resultado.distance_meters > recta, (
        "por carretera nunca es menos que en línea recta"
    )
    assert resultado.distance_meters < recta * 5, (
        f"{resultado.distance_meters} m frente a {recta} m en línea recta: "
        "sospecha de coordenadas invertidas"
    )


@sin_primario
async def test_a_waypoint_outside_the_graph_is_a_permanent_failure():
    """Un punto fuera del grafo cargado: fallo **permanente**, y eso importa.

    Aquí hay un hallazgo medido contra el motor real, no una suposición. Sin
    límite de ajuste, OSRM **ajusta cualquier coordenada** a la carretera más
    cercana del grafo que tenga: con el extracto de Mónaco desplegado, un punto
    de Berlín devolvió `Ok` y 10,1 km de "ruta". Un número plausible de un sitio
    que no es — el modo de fallo que no rompe nada y miente.

    Con `radiuses` el motor responde `NoSegment`, que es la verdad, y el
    adaptador lo clasifica como permanente: §25 hace depender de eso el estado
    terminal, y reintentar una pregunta cuya respuesta no va a cambiar sólo
    retrasa el `Not Calculable`.

    Mi primera versión de este test usaba un punto en el mar frente a Mónaco y
    esperaba que fallara. No falla: el mar está a pocos kilómetros de la costa y
    el ajuste lo lleva a la carretera. El motor tenía razón y la premisa era mía.
    """
    berlin = Punto(Decimal("52.520000"), Decimal("13.405000"))

    with pytest.raises(RoutingUnavailable) as fallo:
        await _router_primario().distance(A, berlin)

    assert fallo.value.transient is False, (
        "fuera del grafo es permanente: repetirlo da lo mismo"
    )
    assert "snap radius" in str(fallo.value)


@sin_primario
async def test_without_a_snap_radius_the_engine_invents_a_plausible_route():
    """El hallazgo, fijado como test: sin radio, el motor miente y parece cierto.

    Está aquí para que nadie quite `radiuses` pensando que es una optimización.
    Sin él, dos puntos separados 1.000 km en línea recta devuelven ~10 km de
    ruta, y la única red que lo atrapa después es la comprobación geométrica de
    plausibilidad — que sí lo atraparía, porque la ruta sale **menor** que la
    línea recta. Las dos defensas existen a propósito; ésta fija la primera.
    """
    sin_radio = OsrmRouter(PRIMARIO, timeout=20.0)
    berlin = Punto(Decimal("52.520000"), Decimal("13.405000"))

    resultado = await sin_radio.distance(A, berlin)
    recta = haversine_meters(A, berlin)

    assert resultado.distance_meters < recta, (
        "la ruta inventada es menor que la línea recta, que es imposible: "
        "por eso la plausibilidad geométrica es la segunda defensa"
    )


@sin_primario
async def test_an_unreachable_primary_is_transient():
    """Un motor que no contesta es un fallo **transitorio**.

    Es la otra mitad de la clasificación, y la que decide si la reserva se
    intenta. Se apunta a un puerto cerrado en localhost, así que el fallo es
    real y no simulado con un doble.
    """
    caido = OsrmRouter("http://127.0.0.1:1", timeout=2.0)

    with pytest.raises(RoutingUnavailable) as fallo:
        await caido.distance(A, B)

    assert fallo.value.transient is True


# ── La reserva, de verdad ───────────────────────────────────────────────────


@sin_reserva
async def test_the_fallback_engine_returns_a_credible_road_distance():
    """Valhalla responde y el adaptador convierte kilómetros a metros.

    Se compara con la línea recta igual que el primario. La conversión de
    unidades es el punto: Valhalla devuelve kilómetros y el dominio espera
    metros, así que un adaptador que se olvidara de multiplicar daría una
    distancia mil veces menor — y ésa sería **menor que la línea recta**, que
    es lo que atrapa la aserción.
    """
    resultado = await _router_reserva().distance(A, B)
    recta = haversine_meters(A, B)

    assert resultado.provider == "valhalla"
    assert resultado.distance_meters > recta
    assert resultado.distance_meters < recta * 5


@sin_primario
@sin_reserva
async def test_the_two_engines_agree_within_a_sane_margin():
    """Los dos motores, sobre los mismos datos, dan distancias comparables.

    No idénticas —cada uno elige su ruta— pero del mismo orden. Si difirieran
    en un factor grande, uno de los dos adaptadores estaría mal y la reserva
    produciría kilometraje incoherente con el primario, que es peor que no
    tener reserva.
    """
    primario = await _router_primario().distance(A, B)
    reserva = await _router_reserva().distance(A, B)

    mayor = max(primario.distance_meters, reserva.distance_meters)
    menor = min(primario.distance_meters, reserva.distance_meters)
    assert mayor / menor < Decimal("2"), (
        f"osrm {primario.distance_meters} m vs valhalla "
        f"{reserva.distance_meters} m: divergen demasiado"
    )


# ── La cadena ───────────────────────────────────────────────────────────────


@sin_reserva
async def test_a_down_primary_falls_through_to_the_fallback():
    """Primario caído → la reserva responde → hay distancia.

    Éste es el camino que §5 exige que esté **ejercitado** y no sólo diseñado.
    El primario apunta a un puerto cerrado, así que su caída es real.
    """
    cadena = FallbackRouter(
        OsrmRouter("http://127.0.0.1:1", timeout=2.0), _router_reserva()
    )

    resultado = await cadena.distance(A, B)

    assert resultado.provider == "valhalla", (
        "la provenance registra el proveedor **usado**, no el configurado (§23)"
    )
    assert resultado.distance_meters > 0


@sin_primario
async def test_a_permanent_primary_failure_does_not_consult_the_fallback():
    """Un fallo permanente del primario **no** se le pregunta a la reserva.

    Sobre los mismos datos OSM la respuesta sería la misma, así que intentarlo
    convertiría un terminal honesto en un intento más. Se comprueba con una
    reserva que llevaría la cuenta: no debe recibir ninguna llamada.
    """
    berlin = Punto(Decimal("52.520000"), Decimal("13.405000"))

    class _ReservaQueCuenta:
        name = "counting"

        def __init__(self) -> None:
            self.llamadas = 0

        async def distance(self, origen, destino):
            self.llamadas += 1
            raise RoutingUnavailable("no debería llamarse", transient=True)

    reserva = _ReservaQueCuenta()
    cadena = FallbackRouter(_router_primario(), reserva)

    with pytest.raises(RoutingUnavailable) as fallo:
        await cadena.distance(A, berlin)

    assert reserva.llamadas == 0, "un permanente no se reintenta en otro motor"
    assert fallo.value.transient is False


async def test_both_engines_down_is_a_transient_chain_failure():
    """Los dos caídos → fallo transitorio que nombra a los dos.

    No necesita motores reales: los dos extremos son puertos cerrados, que es
    una caída de verdad. Lo que importa es que el mensaje conserve la
    información de ambos, porque diagnosticar con la mitad es adivinar.
    """
    cadena = FallbackRouter(
        OsrmRouter("http://127.0.0.1:1", timeout=2.0),
        ValhallaRouter("http://127.0.0.1:2", timeout=2.0),
    )

    with pytest.raises(RoutingUnavailable) as fallo:
        await cadena.distance(A, B)

    mensaje = str(fallo.value)
    assert "primary(osrm)" in mensaje
    assert "fallback(valhalla)" in mensaje
    assert fallo.value.transient is True


# ── Un viaje entero con el motor real ───────────────────────────────────────


@sin_primario
async def test_a_multi_segment_trip_sums_real_road_distances():
    """Tres waypoints, dos tramos, con el motor real.

    Es el caso del Change Plan medido de verdad: la suma de los dos tramos
    tiene que ser **mayor o igual** que el tramo directo, porque desviarse no
    acorta. Si el adaptador mezclara los puntos, esta desigualdad se rompería.
    """
    motor = _router_primario()

    directo = await motor.distance(A, B)
    primero = await motor.distance(A, C)
    segundo = await motor.distance(C, B)
    via_c = primero.distance_meters + segundo.distance_meters

    assert via_c >= directo.distance_meters, (
        f"pasar por C ({via_c} m) no puede ser más corto que ir directo "
        f"({directo.distance_meters} m)"
    )
    for tramo in (primero, segundo):
        assert tramo.provider == "osrm"
        assert tramo.distance_meters > 0
