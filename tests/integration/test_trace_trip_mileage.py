"""El trazador de kilometraje: que diga la verdad y que no escriba nada.

Por qué este archivo existe
----------------------------
`app/db/scripts/trace_trip_mileage.py` es la herramienta con la que se saca la
traza de campo de un viaje real, y se ejecuta en una consola del entorno
compartido. Un camino que sólo se recorre allí es exactamente el que no
conviene estrenar allí: si imprime mal un estado, quien lo lea clasificará mal
el incidente; si escribiera algo, lo haría sobre datos de producción.

Así que aquí se ejercita con un viaje **calculado de verdad** —motor de
kilometraje incluido— y se comprueban las dos promesas que el comando hace:

1. la traza contiene lo que el cierre de campo pide (estado, metros, millas,
   proveedor, tramos, evidencia de cada waypoint);
2. no escribe. Se fotografía la tabla antes y después, y también
   `audit_event`, que es donde aparecería cualquier intento.

Y una tercera, de privacidad: las coordenadas **no** salen por omisión, porque
la salida del comando acaba pegada en documentos y un waypoint es la ubicación
de una persona en un momento concreto.

Por qué importa los ayudantes del suite cross-surface
------------------------------------------------------
Construir un viaje calculado son unas 120 líneas de preparación real
—supervisor, vehículo, jornada, odómetro, viaje, actividad, dos puntos de
ubicación— que ese archivo ya tiene escritas y mantenidas. Copiarlas aquí daría
dos versiones de la misma preparación que se separarían con el primer cambio
del dominio.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import async_session_maker
from app.db.scripts.trace_trip_mileage import pendientes, recientes, traza
from tests.integration.test_mileage_cross_surface import (  # noqa: F401
    MILLAS_ESPERADAS,
    router_fijo,
)
from tests.integration.test_mileage_cross_surface import (
    _abrir_jornada,
    _calcular,
    _estado_de,
    _supervisor,
    _vencer_reintentos,
    _viaje_con_evidencia,
)

pytestmark = pytest.mark.integration

#: Las coordenadas que `_viaje_con_evidencia` captura. Si aparecen en la salida
#: por omisión, la promesa de privacidad está rota.
LATITUD_DE_SALIDA = "33.95"


async def _foto_de_la_base() -> tuple[list, int]:
    """Lo que tendría que cambiar si el comando escribiera."""
    async with async_session_maker() as session:
        filas = (
            await session.execute(
                text(
                    "SELECT id, state, total_meters, attempt_count, next_attempt_at, "
                    "last_error, updated_at FROM trip_mileage ORDER BY id"
                )
            )
        ).all()
        eventos = await session.scalar(text("SELECT count(*) FROM audit_event"))
    return [tuple(f) for f in filas], eventos


async def _un_viaje_calculado(alpha_client, seeded) -> dict:
    await _supervisor(alpha_client, seeded, unidad="V-TRAZA")
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()
    estado, metros = await _estado_de(viaje["id"])
    assert estado == "calculated", f"la preparación no calculó: {estado}"
    assert metros == Decimal("20000.00"), metros
    return viaje


async def test_la_traza_contiene_lo_que_el_cierre_de_campo_pide(
    seeded, alpha_client, router_fijo, capsys
):
    """La cadena completa, de tenant a tramo, en una sola salida."""
    viaje = await _un_viaje_calculado(alpha_client, seeded)
    capsys.readouterr()

    await traza(viaje["id"], coordenadas=False)
    salida = capsys.readouterr().out

    for esperado in (
        "tenant          : alpha",
        f"viaje           : id={viaje['id']}",
        "estado=calculated",
        "total_meters  : 20000.00",
        f"{MILLAS_ESPERADAS} millas",
        "proveedor=fijo/test/1",
        "start_trip",
        "arrived",
        "tramos        : 1",
    ):
        assert esperado in salida, (
            f"la traza no contiene '{esperado}'.\n--- salida ---\n{salida}"
        )

    # Un viaje calculado no tiene razón terminal ni error, y la traza lo dice
    # con un guión en vez de dejar el campo en blanco.
    assert "terminal      : -" in salida
    assert "ultimo error  : -" in salida


async def test_las_coordenadas_no_salen_por_omision(
    seeded, alpha_client, router_fijo, capsys
):
    """Presencia y nivel de evidencia sí; la ubicación, sólo si se pide."""
    viaje = await _un_viaje_calculado(alpha_client, seeded)
    capsys.readouterr()

    await traza(viaje["id"], coordenadas=False)
    callada = capsys.readouterr().out
    assert LATITUD_DE_SALIDA not in callada, (
        "la traza imprimió una coordenada sin que se pidiera"
    )
    assert "presente nivel=fresh" in callada

    await traza(viaje["id"], coordenadas=True)
    explicita = capsys.readouterr().out
    assert LATITUD_DE_SALIDA in explicita, (
        "--coordenadas no mostró las coordenadas, así que el control de "
        "privacidad no está realmente controlando nada"
    )


async def test_el_comando_no_escribe_nada(
    seeded, alpha_client, router_fijo, capsys
):
    """Las tres salidas, y la base idéntica antes y después.

    El control positivo de este test es el otro: si `traza` no imprimiera la
    cifra, comparar la base no probaría nada.
    """
    viaje = await _un_viaje_calculado(alpha_client, seeded)
    antes = await _foto_de_la_base()
    capsys.readouterr()

    await traza(viaje["id"], coordenadas=True)
    await recientes(seeded.alpha.id, 20)
    await pendientes(seeded.alpha.id)
    capsys.readouterr()

    assert await _foto_de_la_base() == antes, (
        "el trazador cambió el estado de la base o dejó un evento de auditoría"
    )


async def test_el_listado_reciente_muestra_el_estado_del_viaje(
    seeded, alpha_client, router_fijo, capsys
):
    """La lista es lo primero que se ejecuta cuando no se sabe qué viaje mirar."""
    viaje = await _un_viaje_calculado(alpha_client, seeded)
    capsys.readouterr()

    await recientes(seeded.alpha.id, 20)
    salida = capsys.readouterr().out

    assert str(viaje["id"]) in salida
    assert "calculated" in salida
    assert MILLAS_ESPERADAS in salida


async def test_el_atraso_distingue_esperando_de_vencido(
    seeded, alpha_client, capsys
):
    """Sin motor, el viaje queda pendiente — y el atraso dice por qué y hasta cuándo.

    Éste es el caso del entorno compartido: evidencia intacta y ningún motor de
    carretera. Las dos ramas importan y son distintas:

    * **espera hasta** — el reintento acotado está programado. Normal.
    * **VENCIDO** — ya tocaba y sigue ahí, que es lo que se ve cuando el barrido
      no está corriendo.

    Confundirlas haría que un scheduler caído pareciera un pendiente sano, que
    es justo el diagnóstico que este cierre tiene que poder hacer.
    """
    await _supervisor(alpha_client, seeded, unidad="V-PEND")
    await _abrir_jornada(alpha_client, seeded)
    viaje = await _viaje_con_evidencia(alpha_client, company_id=seeded.alpha.id)
    await _calcular()

    estado, _ = await _estado_de(viaje["id"])
    assert estado == "pending_calculation", (
        f"sin motor configurado el estado debería ser pendiente, no {estado}"
    )

    # Rama 1: el intento falló de forma transitoria y el reintento quedó
    # programado hacia adelante.
    capsys.readouterr()
    await pendientes(seeded.alpha.id)
    esperando = capsys.readouterr().out

    assert "pending_calculation" in esperando
    assert f"viaje {viaje['id']}" in esperando
    assert "espera hasta" in esperando
    assert "VENCIDO" not in esperando
    assert "No road routing engine is configured" in esperando, (
        "el atraso no explicó por qué el viaje sigue pendiente"
    )

    # Rama 2: vence el reintento y el mismo viaje pasa a ser trabajo debido.
    await _vencer_reintentos()
    capsys.readouterr()
    await pendientes(seeded.alpha.id)
    vencido = capsys.readouterr().out

    assert "VENCIDO" in vencido, (
        "un reintento ya vencido no se declaró debido, así que un barrido "
        f"detenido pasaría por normal.\n--- salida ---\n{vencido}"
    )


async def test_un_viaje_que_no_existe_se_dice_y_no_revienta(seeded, capsys):
    """Un id equivocado en una consola de producción no puede dar una traza."""
    await traza(10**9, coordenadas=False)
    assert "No existe ningun viaje" in capsys.readouterr().out
