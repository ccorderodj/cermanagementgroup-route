"""
Superficie pública de la API.

**Regla de arquitectura, permanente:**

    Un router público puede incluir endpoints públicos.
    Nunca un router de dominio que mezcle endpoints públicos y privados.

Antes esto era:

    api_router_public.include_router(router_users)     # el router ENTERO
    api_router_public.include_router(router_regions)   # el router ENTERO

y publicaba sin autenticación `register`, `change-password` y tres endpoints de
`regions` que devolvían datos del tenant a cualquiera que conociera el
subdominio. El defecto no era un olvido: era estructural, porque cualquier
endpoint añadido después a esos módulos quedaba publicado solo (AUD-SEC-002).

Lo que hay aquí es una lista blanca. Añadir algo exige escribirlo, y escribirlo
obliga a justificarlo.
"""

from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.core.schemas.error import ErrorResponse
from app.routers_api.users.public_router import router as public_auth_router


api_router_public = APIRouter(
    default_response_class=JSONResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    prefix="/public",
)


# ── Lista blanca de endpoints públicos ──────────────────────────────────────
#
#   POST /api/public/auth/login                     iniciar sesión
#   POST /api/public/auth/logout                    cerrar sesión (borra cookies)
#   POST /api/public/auth/password-reset            pedir enlace de recuperación
#   POST /api/public/auth/password-reset/confirm    canjear el enlace
#
# Todos siguen exigiendo un subdominio de compañía válido: el tenant se resuelve
# antes en `CompanyResolverMiddleware`.
api_router_public.include_router(public_auth_router)
