"""Un cero con motivo: que la pantalla distinga «no condujo» de «no se pudo medir».

El problema que cierra este archivo
------------------------------------
Today / Live publicaba dos datos de kilometraje: las millas y si quedaba algo
pendiente. Con eso, **tres** realidades se dibujaban idénticas:

    no hubo ningún viaje             ->  0.0 mi
    faltó evidencia de ubicación     ->  0.0 mi      `not_calculable`
    el routing agotó su reintento    ->  0.0 mi      `calculation_failed`

Un supervisor que condujo sesenta kilómetros y perdió el GPS se veía exactamente
igual que uno que no salió de la oficina. El cero era veraz —esos viajes no
tienen kilometraje y no se les va a inventar uno— pero mudo, y un cero mudo
obliga a abrir una consola de producción para saber qué pasó. Ocurrió en campo.

Lo que **no** cambia, y hay tests que lo fijan
-----------------------------------------------
Ninguna cifra. Un viaje sin resolver sigue aportando cero a las millas oficiales
y sigue sin recibir ninguna distancia estimada. Lo único que se añade es la
pregunta que faltaba: *¿el cero es porque no hubo recorrido, o porque no se pudo
medir?*
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.routers_api.mileage.routing import RoutingUnavailable, set_road_router
from tests.integration.test_mileage_cross_surface import (
    _abrir_jornada,
    _calcular,
    _estado_de,
    _live,
    _supervisor,
    _viaje_con_evidencia,
)
from tests.integration.test_mileage_data_to_ux import (
    METROS_DISCRIMINANTES,
    MILLAS_EXACTAS,
    RouterDeDistanciaFija,
)

pytestmark = pytest.mark.integration


class RouterQueRechaza:
    """Rechaza de forma **permanente**: la pregunta no mejora repitiéndola.

    Es el camino corto a `calculation_failed`. El largo —agotar los diez
    intentos acotados— produce el mismo estado terminal y tarda diez barridos;
    lo que este archivo comprueba es cómo se **presenta** ese estado, no cómo se
    llega a él, que ya tiene sus tests en el motor.
    """

    name = "rechaza"

    async def distance(self, origen, destino):
        raise RoutingUnavailable("provider rejected the query", transient=False)


async def _fila_del_supervisor(alpha_client, seeded):
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    datos = await _live(alpha_client)
    return next(
        s
        for s in datos["supervisors"]
        if s["user_id"] == seeded.alpha.users["supervisor"].id
    ), datos


async def _declarar_sin_ubicacion(alpha_client, viaje_id: int, kind: str) -> None:
    """El cliente agotó su ventana y lo dice. Es el camino real de campo."""
    respuesta = await alpha_client.post(
        "/api/location/missing",
        json={
            "event_kind": kind,
            "subject_id": viaje_id,
            "reason_code": "permission_denied",
        },
    )
    assert respuesta.status_code == 201, respuesta.text


# ── El estado terminal por falta de evidencia ───────────────────────────────


async def test_un_viaje_sin_evidencia_se_declara_sin_resolver(seeded, alpha_client):
    """`not_calculable` deja de ser un cero mudo.

    El supervisor salió y llegó, pero su teléfono no dio ubicación en ninguno de
    los dos extremos. Sin los dos puntos no hay distancia que pedir a ningún
    proveedor: es terminal, es veraz, y hasta ahora era indistinguible de no
    haber conducido.
    """
    fijo = RouterDeDistanciaFija(METROS_DISCRIMINANTES)
    previo = set_road_router(fijo)
    try:
        await _supervisor(alpha_client, seeded, unidad="V-SINGPS")
        await _abrir_jornada(alpha_client, seeded)
        viaje = await _viaje_con_evidencia(
            alpha_client, company_id=seeded.alpha.id, con_evidencia=False
        )
        await _declarar_sin_ubicacion(alpha_client, viaje["id"], "start_trip")
        await _declarar_sin_ubicacion(alpha_client, viaje["id"], "arrived")
        await _calcular()
    finally:
        set_road_router(previo)

    estado, metros = await _estado_de(viaje["id"])
    assert estado == "not_calculable", estado
    assert metros is None or Decimal(metros) == 0

    fila, _ = await _fila_del_supervisor(alpha_client, seeded)
    assert fila["official_miles"] == "0.0"
    assert fila["mileage_pending"] is False, (
        "un estado terminal no puede anunciarse como 'todavía calculando'"
    )
    assert fila["mileage_unresolved"] == 1, (
        "el viaje terminó sin cifra y la pantalla no lo dice: vuelve el cero mudo"
    )


# ── El estado terminal por fallo del proveedor ──────────────────────────────


async def test_un_viaje_con_routing_fallido_se_declara_sin_resolver(
    seeded, alpha_client
):
    """`calculation_failed` también. Es el caso que apareció en campo.

    La evidencia estaba completa; el que no pudo fue el proveedor. El barrido
    **no** recoge estados terminales —por diseño—, así que conectar el motor
    después no lo recupera solo: hay que reponerlo con
    `reprocess_failed_mileage`. Razón de más para que se vea.
    """
    previo = set_road_router(RouterQueRechaza())
    try:
        await _supervisor(alpha_client, seeded, unidad="V-FALLO")
        await _abrir_jornada(alpha_client, seeded)
        viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
        await _calcular()
    finally:
        set_road_router(previo)

    estado, _ = await _estado_de(viaje["id"])
    assert estado == "calculation_failed", estado

    async with async_session_maker() as session:
        razon = await session.scalar(
            text("SELECT terminal_reason FROM trip_mileage WHERE trip_id = :t"),
            {"t": viaje["id"]},
        )
    assert razon == "routing_exhausted", razon

    fila, _ = await _fila_del_supervisor(alpha_client, seeded)
    assert fila["official_miles"] == "0.0"
    assert fila["mileage_pending"] is False
    assert fila["mileage_unresolved"] == 1


# ── Que no se confundan entre sí ni con lo calculado ────────────────────────


async def test_calculado_pendiente_y_sin_resolver_son_tres_cosas_distintas(
    seeded, alpha_client
):
    """Los tres a la vez, en una sola jornada. Es la prueba que importa.

    Si los tres estados se mezclaran, la pantalla volvería a mentir — y con una
    mentira peor, porque ahora tendría un marcador que la respalda.
    """
    fijo = RouterDeDistanciaFija(METROS_DISCRIMINANTES)
    previo = set_road_router(fijo)
    try:
        await _supervisor(alpha_client, seeded, unidad="V-TRES")
        await _abrir_jornada(alpha_client, seeded)

        # 1. Uno que calcula.
        calculado = await _viaje_con_evidencia(
            alpha_client, company_id=seeded.alpha.id
        )
        await _calcular()
        assert (await _estado_de(calculado["id"]))[0] == "calculated"

        # 2. Uno sin evidencia declarada: terminal, sin cifra.
        #
        # Lleva actividad **a propósito**: un viaje que llega y no ejecuta nada
        # se queda en `arrived` y no cierra, y entonces el siguiente `POST
        # /api/trips` devuelve ese mismo viaje en vez de crear otro. Sin esto,
        # el tercer caso no existiría y el test pasaría comprobando dos.
        sin_gps = await _viaje_con_evidencia(
            alpha_client,
            company_id=seeded.alpha.id,
            referencia="XYZ Logistics",
            con_evidencia=False,
        )
        await _declarar_sin_ubicacion(alpha_client, sin_gps["id"], "start_trip")
        await _declarar_sin_ubicacion(alpha_client, sin_gps["id"], "arrived")
        await _calcular()
        assert (await _estado_de(sin_gps["id"]))[0] == "not_calculable"

        # 3. Uno que todavía espera su evidencia: pendiente de verdad.
        pendiente = await _viaje_con_evidencia(
            alpha_client,
            company_id=seeded.alpha.id,
            referencia="ABC Manufacturing",
            con_evidencia=False,
            con_actividad=False,
        )
        assert pendiente["id"] not in (calculado["id"], sin_gps["id"]), (
            "no se creó un tercer viaje: el anterior seguía abierto"
        )
        await _calcular()
        assert (await _estado_de(pendiente["id"]))[0] == "pending_calculation"
    finally:
        set_road_router(previo)

    fila, datos = await _fila_del_supervisor(alpha_client, seeded)

    assert fila["official_miles"] == MILLAS_EXACTAS, (
        "las millas del viaje calculado se perdieron entre los otros dos"
    )
    assert fila["mileage_pending"] is True, "el viaje que sí espera no se anunció"
    assert fila["mileage_unresolved"] == 1, (
        "el viaje terminal se contó mal: debe ser exactamente uno"
    )
    assert datos["summary"]["total_miles"] == MILLAS_EXACTAS


async def test_un_dia_sin_viajes_no_inventa_nada_que_resolver(seeded, alpha_client):
    """El control del conjunto: sin viajes, cero y **sin** marcador.

    Sin este test, un `mileage_unresolved` que devolviera siempre 1 pasaría
    todas las comprobaciones de arriba. Aquí es donde el número tiene que ser 0.
    """
    await _supervisor(alpha_client, seeded, unidad="V-VACIO")
    await _abrir_jornada(alpha_client, seeded)

    fila, _ = await _fila_del_supervisor(alpha_client, seeded)
    assert fila["official_miles"] == "0.0"
    assert fila["mileage_pending"] is False
    assert fila["mileage_unresolved"] == 0, (
        "una jornada sin viajes no tiene nada sin resolver"
    )


async def test_lo_sin_resolver_no_aporta_distancia(seeded, alpha_client):
    """Lo que este cambio **no** puede hacer: convertirse en millas.

    Un viaje sin cifra sigue sumando cero. Si alguna vez aportara una distancia
    estimada, esto lo detiene: sería odómetro o línea recta disfrazados de
    kilometraje oficial, que es lo que RTE06 prohíbe.
    """
    previo = set_road_router(RouterQueRechaza())
    try:
        await _supervisor(alpha_client, seeded, unidad="V-CERO")
        await _abrir_jornada(alpha_client, seeded)
        viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
        await _calcular()
    finally:
        set_road_router(previo)

    assert (await _estado_de(viaje["id"]))[0] == "calculation_failed"

    fila, datos = await _fila_del_supervisor(alpha_client, seeded)
    assert Decimal(fila["official_miles"]) == Decimal("0.0")
    assert Decimal(datos["summary"]["total_miles"]) == Decimal("0.0")
