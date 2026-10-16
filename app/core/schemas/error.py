"""
Forma de las respuestas de error.

Una sola definición para toda la API. Antes convivían `Error`/`AttrError` aquí
—sin ningún consumidor— con un `ErrorResponse` duplicado en cada agregador de
routers (AUD-BE-021).
"""

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Envoltorio uniforme: `{"detail": ...}`.

    `detail` admite tanto un texto —lo que produce `HTTPException`— como la
    lista de errores de campo que genera la validación de FastAPI.
    """

    detail: Any
