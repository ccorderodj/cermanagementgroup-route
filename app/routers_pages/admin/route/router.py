"""
Configuración de CER Route en el shell de administración.

Las dos pantallas que RTE02 entrega funcionando: vehículos (con sus
asignaciones) y listas estandarizadas. Cada una exige en el servidor la misma
capacidad que exige su API, para que el enlace no lleve a una pantalla que
después devuelve 403 (AUD-FE-013).

Today/Live, Activity y Reports **no se registran aquí**. Son de checkpoints
posteriores, y una ruta registrada con una pantalla vacía sería exactamente lo
que las instrucciones prohíben: representar como implementado algo que no lo
está.
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
