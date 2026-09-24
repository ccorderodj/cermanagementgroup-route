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
from app.routers_api.usermanagement.router import router as router_usermanagement
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.router import router as router_users

# Catálogos geográficos
from app.routers_api.regions.router import router as router_regions

# CER Route: configuración operativa del dominio de campo.
from app.routers_api.standardvalues.router import router as router_standard_values
from app.routers_api.vehicles.router import router as router_vehicles
from app.routers_api.vehicles.router import supervisors_router as router_supervisors
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
api_router.include_router(router_companies)
api_router.include_router(router_regions)
api_router.include_router(router_integrations)

api_router.include_router(router_vehicles)
api_router.include_router(router_supervisors)
api_router.include_router(router_standard_values)
api_router.include_router(router_worksessions)
api_router.include_router(router_trips)

api_router.include_router(router_platform_settings)
api_router.include_router(router_platform_diagnostics)
