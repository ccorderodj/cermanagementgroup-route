from fastapi import APIRouter, Request

from app.core.utils.web_routers import (
    CheckNameRoute,
    CustomTemplates,
)

router = APIRouter(
    prefix="/profile",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get("", name="ProfilePage")
async def get_profile_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="profile/index.html",
        context={},
    )