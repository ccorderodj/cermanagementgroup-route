"""
Quién dispara el envío automático de los correos de actividad (RTE-MAIL-CP4-01).

Dos relojes, un solo despacho (`delivery.despachar_vencidos`)
-------------------------------------------------------------
* **El programador interno** (`PlatformScheduler`), **cada minuto** y sólo en la
  réplica líder (candado de PostgreSQL). Es el que da la precisión: un correo
  de fin de jornada sale como mucho un minuto después de «End Work + 20 min».
* **El Scheduled Job de DigitalOcean**, cada 15 minutos (el mínimo que permite
  App Platform), con este mismo módulo y `--once`. Es el **reconciliador**: si
  la app web estuvo caída o reiniciándose, recoge lo que venció y no salió.

Los dos llaman a lo mismo y reservan sobre la misma clave única, así que si
coinciden no se duplica nada: el segundo encuentra la entrega ya reservada o
aceptada.

Los interruptores mandan sobre los dos: `MAIL_AUTOMATION_ENABLED` (apagado por
defecto) y `MAIL_AUTOMATION_DRY_RUN` (encendido por defecto: sólo cuenta y
registra en el log qué haría).

Uso desde el cron (y para probarlo a mano en la consola)::

    python -m app.routers_api.activityemails.jobs --once

Termina con código 0 si la pasada se completó (aunque algún envío fallara y
quede para reintento) y 1 si la pasada misma no pudo hacerse.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.logger import logger
from app.routers_api.activityemails.models import DeliverySource


async def despachar_desde_el_programador() -> None:
    from app.routers_api.activityemails.delivery import despachar_vencidos

    await despachar_vencidos(source=DeliverySource.SCHEDULE.value)


def register_activity_email_jobs() -> None:
    """Registra el despacho en el programador interno, cada minuto.

    Siempre se registra: con `MAIL_AUTOMATION_ENABLED` apagado, la pasada vuelve
    sin consultar nada, y así encenderlo no exige reiniciar la app.
    """
    from app.core.platform.scheduler import platform_scheduler

    platform_scheduler.register(
        "activity_email_dispatch",
        despachar_desde_el_programador,
        trigger="interval",
        minutes=1,
    )


async def _una_pasada() -> int:
    from app.db.model_registry import load_all_models

    load_all_models()
    from app.core.platform.config_service import platform_config
    from app.routers_api.activityemails.delivery import despachar_vencidos

    # El proveedor de correo vive en Platform Settings: hay que cargarlo como
    # hace la app al arrancar.
    await platform_config.refresh()
    resumen = await despachar_vencidos(source=DeliverySource.RECONCILE.value)
    print(resumen.linea())
    for linea in resumen.detalle[:50]:
        print("  ", linea)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envío de los correos de actividad que vencieron.")
    parser.add_argument("--once", action="store_true", required=True, help="Una pasada y termina.")
    parser.parse_args(argv)
    try:
        return asyncio.run(_una_pasada())
    except Exception:
        logger.exception("MAIL DISPATCH | la pasada no pudo completarse")
        return 1


if __name__ == "__main__":
    sys.exit(main())
