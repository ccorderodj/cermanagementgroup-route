"""
Traducción de excepciones a respuestas.

Dos reglas:

**1. Lo que sale al cliente está saneado.** Antes se devolvía el mensaje crudo
de SQLAlchemy cuando no encontraba una línea `DETAIL:`, así que una petición
anónima llegaba a leer `"Unconsumed column names: hashed_password"` — nombres de
columna e internals del ORM (AUD-BE-003). Ahora el diagnóstico va al log y al
cliente le llega qué salió mal, no cómo está construido el sistema.

**2. Nada se pierde en silencio.** La rama genérica construía un 500 sin llamar
al logger, así que un fallo inesperado desaparecía sin dejar rastro
(AUD-BE-024). Es el peor comportamiento posible para depurar una remediación.

Los códigos también se corrigieron: una violación de unicidad es un **409**, no
un 422. El 422 queda para lo que de verdad es un problema del cuerpo enviado.
"""

import uuid

from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logger import logger


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            return await call_next(request)

        except IntegrityError as exc:
            return self._handled(
                request,
                exc,
                status.HTTP_409_CONFLICT,
                "The operation conflicts with existing data.",
            )

        except SQLAlchemyError as exc:
            return self._handled(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "A database error prevented completing the request.",
            )

        except ValidationError as exc:
            return self._handled(
                request,
                exc,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "The submitted data is not valid.",
            )

        except Exception as exc:  # noqa: BLE001 - red de seguridad final
            return self._handled(
                request,
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "An unexpected error prevented completing the request.",
            )

    @staticmethod
    def _handled(
        request: Request,
        exc: Exception,
        status_code: int,
        public_detail: str,
    ) -> JSONResponse:
        """Registra el fallo completo y devuelve una respuesta sin detalles.

        El identificador permite cruzar lo que vio el usuario con la traza del
        log sin exponer nada en la respuesta.
        """
        error_id = uuid.uuid4().hex[:12]

        logger.error(
            "REQUEST FAILED | id=%s method=%s path=%s status=%s type=%s",
            error_id,
            request.method,
            request.url.path,
            status_code,
            type(exc).__name__,
            exc_info=True,
        )

        return JSONResponse(
            status_code=status_code,
            content={"detail": public_detail, "error_id": error_id},
        )
