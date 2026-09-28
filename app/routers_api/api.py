"""
Superficie privada de la API.

Todo lo que cuelga de aquí exige sesión: `Depends(get_current_user)` está a
nivel de router, así que ninguna ruta puede olvidarlo. La autorización fina
—qué permiso hace falta— la declara cada endpoint con `require_permissions`.

Lo que puede usarse sin sesión está en `app/routers_api_public/api.py`, y allí
se enumera endpoint a endpoint.
"""

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.core.schemas.error import ErrorResponse

# Núcleo de identidad y RBAC
from app.routers_api.companies.router import router as router_companies
from app.routers_api.permissions.router import router as router_permissions
from app.routers_api.rolepermissions.router import router as router_rolepermissions
from app.routers_api.rolepermissionsapprovals.router import (
    router as router_rolepermissionsapprovals,
)
from app.routers_api.roles.router import router as router_roles
from app.routers_api.usermanagement.product_context import marcar_contexto_de_route
from app.routers_api.usermanagement.router import router as router_usermanagement
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.router import router as router_users

# Catálogos geográficos
from app.routers_api.regions.router import router as router_regions

# CER Route: configuración operativa del dominio de campo.
from app.routers_api.standardvalues.router import router as router_standard_values
from app.routers_api.vehicles.router import router as router_vehicles
from app.routers_api.vehicles.router import supervisors_router as router_supervisors
from app.routers_api.odometer.router import router as router_odometer
from app.routers_api.trips.router import router as router_trips
from app.routers_api.worksessions.router import router as router_worksessions


# Integraciones del tenant: administración de webhooks (API interna).
from app.core.integration.admin_router import router as router_integrations

# Plataforma: configuracion e integraciones del despliegue. No es de tenant,
# y por eso sus endpoints exigen administracion de plataforma.
from app.routers_api.platform.settings_router import router as router_platform_settings
from app.routers_api.platform.diagnostics_router import router as router_platform_diagnostics


api_router = APIRouter(
    default_response_class=JSONResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(get_current_user)],
)


api_router.include_router(router_roles)
api_router.include_router(router_permissions)
api_router.include_router(router_rolepermissions)
api_router.include_router(router_rolepermissionsapprovals)
api_router.include_router(router_users)
api_router.include_router(router_usermanagement)
# El **mismo** router, montado otra vez bajo el contrato de CER Route.
#
# No es una segunda administración de usuarios: son los mismos handlers, el mismo
# DAO y la misma auditoría. Lo único que añade la dependencia es marcar que la
# petición llegó por una pantalla de CER Route, y eso acota los roles asignables
# a los dos del producto — para cualquiera que use este contrato, Superadmin
# incluido (PD-02).
#
# La frontera la decide la ruta y no una cabecera: confiar en que el cliente
# declare su propio contexto sería confiar en el cliente para decidir una
# frontera. `/api/users` no cambia.
api_router.include_router(
    router_usermanagement,
    prefix="/route",
    dependencies=[Depends(marcar_contexto_de_route)],
)
api_router.include_router(router_companies)
api_router.include_router(router_regions)
api_router.include_router(router_integrations)

api_router.include_router(router_vehicles)
api_router.include_router(router_supervisors)
api_router.include_router(router_standard_values)
api_router.include_router(router_worksessions)
api_router.include_router(router_trips)
api_router.include_router(router_odometer)

api_router.include_router(router_platform_settings)
api_router.include_router(router_platform_diagnostics)
