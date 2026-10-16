from fastapi import APIRouter, Depends, Request

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates
from app.routers_pages.dependencies import require_page_permissions


router = APIRouter(
    prefix="/locations",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get(
    "/states",
    name="LocationsStatesPage",
    dependencies=[Depends(require_page_permissions(["regions.read"]))],
)
async def get_locations_states_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/locations/states.html",
        context={},
    )
