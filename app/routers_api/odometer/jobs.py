"""
Purga de fotografías de odómetro vencidas, sobre el scheduler que ya existe.

Por qué esto existe, dicho sin adornos
---------------------------------------
No es una política de retención elegida por el negocio. Es la consecuencia de
una limitación del entorno: en App Platform el disco del contenedor es efímero
y el despliegue del piloto no tiene almacenamiento de objetos configurado, así
que la foto **se pierde igualmente** en el siguiente despliegue — medido, no
supuesto: tres evidencias con `storage_key` y ningún archivo detrás.

Dado eso, purgar a propósito es mejor que perder por accidente. Acota el disco
del contenedor, y convierte la desaparición en una regla conocida con una hora
escrita en la configuración, en vez de en una sorpresa que depende de cuándo
alguien despliegue.

Lo que esto **no** arregla
--------------------------
Pasado el plazo, una evidencia `photo_confirmed` sigue afirmando que está
respaldada por una fotografía que ya no existe. El modelo distingue
`photo_confirmed` de `manual_no_photo` justo por eso, y con retención esa
distinción deja de ser comprobable. Es el coste de la decisión, no un efecto
secundario que se pueda programar para que no ocurra.

Por eso la retención vale `0` por defecto —conservar para siempre— y sólo el
entorno que la necesita la activa. Un despliegue con almacenamiento duradero no
debe heredar esto por descuido.

Qué se borra y qué no
---------------------
Se borra **el archivo**. La fila de evidencia no se toca, y en particular
`storage_key` se conserva: `confirm_reading` decide con él si la lectura es
fotográfica o manual, y vaciarlo convertiría una confirmación tardía en
`manual_exception_confirmed` —exigiendo una aprobación que nadie pidió— por el
mero paso del tiempo. La hora de la purga no puede cambiar la naturaleza de la
evidencia.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: Cada cuánto se barre. Con una retención de 60 minutos, una foto vive entre 60
#: y 70: el plazo es un mínimo, no un instante exacto, y pretender precisión al
#: segundo exigiría un job por archivo.
INTERVALO_DE_BARRIDO_MINUTOS = 10

#: Hasta dónde mira hacia atrás el barrido.
#:
#: Sin este límite, cada pasada recorrería todas las evidencias de la historia
#: para reintentar borrar archivos que ya no están. Siete días es holgado de
#: sobra: el disco donde viven es efímero y no sobrevive ni a un despliegue, así
#: que nada puede quedar fuera de esta ventana y seguir ocupando espacio.
VENTANA_DE_BUSQUEDA_DIAS = 7


async def purge_expired_odometer_photos() -> int:
    """Borra las fotos cuyo plazo venció. Devuelve cuántas retiró.

    Con `ODOMETER_PHOTO_RETENTION_MINUTES = 0` no hace nada y lo dice: es el
    valor por defecto, y un barrido que no encuentra configuración no debe
    comportarse como si la hubiera.
    """
    from sqlalchemy import select

    from app.config import settings
    from app.core.db.session import db_session
    from app.core.storage.base import get_storage
    from app.routers_api.odometer.models import OdometerEvidence

    minutos = settings.ODOMETER_PHOTO_RETENTION_MINUTES
    if minutos <= 0:
        return 0

    ahora = datetime.now(timezone.utc)
    vencidas_antes_de = ahora - timedelta(minutes=minutos)
    desde = ahora - timedelta(days=VENTANA_DE_BUSQUEDA_DIAS)

    async with db_session() as session:
        filas = (
            await session.execute(
                select(OdometerEvidence.id, OdometerEvidence.storage_key).where(
                    OdometerEvidence.storage_key.is_not(None),
                    OdometerEvidence.captured_at.is_not(None),
                    OdometerEvidence.captured_at < vencidas_antes_de,
                    OdometerEvidence.captured_at >= desde,
                )
            )
        ).all()

    if not filas:
        return 0

    almacen = get_storage()
    retiradas = 0
    fallos = 0
    for _, clave in filas:
        try:
            if almacen.delete(clave):
                retiradas += 1
        except Exception:
            # Una clave que no se puede borrar no detiene el resto. El barrido
            # vuelve a pasar en minutos, así que reintentarlo aquí sólo
            # retrasaría las demás.
            fallos += 1
            logger.warning(
                "ODOMETER PURGE | no se pudo retirar una foto", exc_info=True
            )

    logger.info(
        "ODOMETER PURGE | %d candidatas, %d retiradas, %d fallos (retención %d min)",
        len(filas),
        retiradas,
        fallos,
        minutos,
    )
    return retiradas


def register_odometer_jobs() -> None:
    """Registra el barrido, **sólo si hay retención configurada**.

    No registrar nada cuando no aplica es deliberado: un job que despierta cada
    diez minutos para no hacer nada es ruido en los logs de todos los entornos
    que conservan sus fotos, que son los normales.
    """
    from app.config import settings
    from app.core.platform.scheduler import platform_scheduler

    if settings.ODOMETER_PHOTO_RETENTION_MINUTES <= 0:
        return

    platform_scheduler.register(
        "odometer_photo_purge",
        purge_expired_odometer_photos,
        trigger="interval",
        minutes=INTERVALO_DE_BARRIDO_MINUTOS,
    )
    logger.info(
        "ODOMETER PURGE | activa: las fotos se retiran a los %d minutos",
        settings.ODOMETER_PHOTO_RETENTION_MINUTES,
    )
