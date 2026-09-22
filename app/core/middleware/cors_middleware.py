"""
CORS.

Los origenes salen de `CORS_ORIGINS` y, por defecto, la lista esta **vacia**:
la propia aplicacion sirve el frontend, asi que no hay ningun origen cruzado
legitimo. Antes estaba cableado `http://localhost:3000` con
`allow_credentials=True`, un origen de desarrollo que habria viajado tal cual a
produccion (AUD-SEC-024).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


def add(app: FastAPI) -> None:
    origins = settings.cors_origin_list
    if not origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )
