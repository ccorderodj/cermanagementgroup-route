"""Los dos barridos de RTE06, sobre el scheduler que ya existe.

Por qué aquí y no en el scheduler
---------------------------------
`PlatformScheduler.register()` existe para esto. Meter estos jobs dentro de la
clase habría puesto conocimiento de un dominio en la plataforma, y §7 dice que
no se cree un segundo scheduler ni se reescriba el que hay.

Los dos corren **sólo en la instancia líder** —`register` los envuelve en
`_only_leader`—, así que con varias instancias el barrido no se duplica.

Por qué dos y no uno
--------------------
Cierran dos limbos distintos:

* el de **ubicación**: un evento cuya ventana de recuperación venció sin que el
  cliente volviera a decir nada. Sin esto, el kilometraje de ese viaje se
  quedaría esperando un punto que nadie va a mandar;
* el de **kilometraje**: un viaje `pending_calculation` cuyo reintento ya
  venció. Es lo que hace cierto que "ningún viaje queda Pending
  indefinidamente" (§24, caso R3).

El orden importa: primero se cierran los eventos de ubicación, porque es lo que
permite al segundo barrido distinguir "falta evidencia todavía" de "esta
evidencia no va a llegar".
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def sweep_route_location_and_mileage() -> None:
    """Cierra ventanas de ubicación vencidas y empuja el kilometraje pendiente.

    Un solo job para las dos cosas, y en este orden a propósito: si el barrido
    de kilometraje corriera antes, encontraría los mismos viajes esperando una
    evidencia que el otro barrido está a punto de declarar perdida, y gastaría
    un intento del reintento acotado en cada pasada sin poder avanzar.
    """
    from app.routers_api.location.service import sweep_unreported_windows
    from app.routers_api.mileage.service import sweep_pending_mileage

    try:
        cerrados = await sweep_unreported_windows()
    except Exception:
        # Un fallo aquí no puede impedir el barrido de kilometraje: son dos
        # limbos independientes y dejar el segundo sin correr por el primero
        # convertiría un problema en dos.
        logger.warning("ROUTE SWEEP | location window sweep failed", exc_info=True)
        cerrados = -1

    try:
        resumen = await sweep_pending_mileage()
    except Exception:
        logger.warning("ROUTE SWEEP | mileage sweep failed", exc_info=True)
        return

    if cerrados or resumen.get("examined"):
        logger.info(
            "ROUTE SWEEP | missing_finalized=%s mileage=%s", cerrados, resumen
        )


def register_route_jobs() -> None:
    """Registra el barrido en el scheduler de plataforma.

    El intervalo sale de `route_mileage.sweeper_interval_minutes`, así que se
    puede ajustar sin desplegar — igual que los umbrales (§26). Se lee una vez,
    al arrancar: cambiarlo en caliente exigiría reprogramar el job, y eso es
    complejidad que nadie ha pedido.
    """
    from app.core.platform.config_service import platform_config
    from app.core.platform.scheduler import platform_scheduler

    minutos = int(platform_config.policy("route_mileage")["sweeper_interval_minutes"])
    platform_scheduler.register(
        "route_location_mileage_sweep",
        sweep_route_location_and_mileage,
        trigger="interval",
        minutes=minutos,
    )
