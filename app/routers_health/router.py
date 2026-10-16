"""
Sondas de infraestructura (D11).

Viven en la aplicación raíz y `CompanyResolverMiddleware` las exime, porque un
orquestador no tiene por qué conocer el subdominio de ninguna compañía. Antes el
único health check disponible estaba bajo `/api` y detrás del resolutor de
tenant: un `docker healthcheck` o un scrape recibían 404 (AUD-ARCH-003).

Dos sondas, con dos preguntas distintas:

* `/health`        ¿el proceso responde? Sin tocar la base. Es la sonda de
                   *liveness*: si falla, reiniciar el contenedor tiene sentido.
* `/health/ready`  ¿puede atender tráfico? Comprueba la base. Es la de
                   *readiness*: si falla, hay que sacar la instancia del balanceo,
                   pero reiniciarla no arreglaría nada.

Ninguna revela versiones ni detalles internos: son públicas por necesidad.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.database import engine
from app.logger import logger


router = APIRouter(tags=["Infrastructure"], include_in_schema=False)


@router.get("/health")
async def health() -> dict:
    """Liveness. No consulta la base a propósito."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Readiness. Comprueba que la base responde."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        # El motivo queda en el log del servidor, no en la respuesta.
        logger.error("READINESS | la base de datos no responde", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "down"}

    return {"status": "ok", "database": "up"}
