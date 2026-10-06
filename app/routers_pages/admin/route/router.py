"""
Configuración de CER Route en el shell de administración.

Las pantallas de configuración y revisión que Route entrega funcionando:
vehículos (con sus asignaciones), listas estandarizadas y —desde RTE04— la cola
de excepciones de odómetro. Cada una exige en el servidor la misma capacidad que
exige su API, para que el enlace no lleve a una pantalla que después devuelve 403
(AUD-FE-013).

Today / Live entra con RTE07 y su pantalla existe de verdad. Activity y Reports
siguen **sin registrarse**: son de checkpoints posteriores, y una ruta con una
pantalla vacía sería exactamente lo que las instrucciones prohíben —representar
como implementado algo que no lo está.
"""

from fastapi import APIRouter, Depends, Request

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates
from app.routers_pages.dependencies import require_page_permissions


router = APIRouter(
    prefix="/route",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get(
    "/users",
    name="RouteUsersPage",
    # Las capacidades del **núcleo**: esta pantalla administra identidad, no
    # una entidad de Route. No se inventa `route.users.manage` porque el
    # contrato de autorización correcto ya existe.
    dependencies=[Depends(require_page_permissions(["users.read"]))],
)
async def get_route_users_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/users.html",
        context={},
    )


@router.get(
    "/supervisors",
    name="RouteSupervisorsPage",
    dependencies=[Depends(require_page_permissions(["route.vehicles.read"]))],
)
async def get_route_supervisors_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/supervisors.html",
        context={},
    )


@router.get(
    "/today",
    name="RouteTodayLivePage",
    # La misma capacidad que exige `GET /api/live/today`. Pedir aquí una
    # distinta llevaría a una pantalla que después devuelve 403 (AUD-FE-013).
    dependencies=[Depends(require_page_permissions(["route.live.read"]))],
)
async def get_route_today_live_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/today-live.html",
        context={},
    )


@router.get(
    "/activity",
    name="RouteActivityExplorerPage",
    # La misma capacidad que exige `GET /api/activity-explorer`. Pedir aquí una
    # distinta llevaría a una pantalla que después devuelve 403 (AUD-FE-013).
    dependencies=[Depends(require_page_permissions(["route.activity.read"]))],
)
async def get_route_activity_explorer_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/activity.html",
        context={},
    )


@router.get(
    "/vehicles",
    name="RouteVehiclesPage",
    dependencies=[Depends(require_page_permissions(["route.vehicles.read"]))],
)
async def get_route_vehicles_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/vehicles.html",
        context={},
    )


@router.get(
    "/odometer-exceptions",
    name="RouteOdometerExceptionsPage",
    # La misma capacidad que exigen los endpoints de decisión. Pedir aquí una
    # distinta llevaría a una pantalla que después devuelve 403 (AUD-FE-013), y
    # `route.records.adjust` es autoridad de administración a propósito: quien
    # ejecuta la jornada no puede aprobar su propia excepción.
    dependencies=[Depends(require_page_permissions(["route.records.adjust"]))],
)
async def get_route_odometer_exceptions_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/odometer-exceptions.html",
        context={},
    )


@router.get(
    "/standard-values",
    name="RouteStandardValuesPage",
    dependencies=[
        Depends(require_page_permissions(["route.standardvalues.manage"]))
    ],
)
async def get_route_standard_values_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/route/standard-values.html",
        context={},
    )
