"""
Pantallas de compania.

`CompanyListPage` lista todos los tenants, asi que es administracion de
plataforma y no de tenant (D6): la protege `require_platform_admin_page`, no un
permiso del catalogo.
"""

from fastapi import APIRouter, Depends, Request

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates
from app.routers_pages.dependencies import (
    require_page_permissions,
    require_platform_admin_page,
)


router = APIRouter(
    prefix="/companies",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get(
    "/list",
    name="CompanyListPage",
    dependencies=[Depends(require_platform_admin_page())],
)
async def get_company_list_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/companies/list.html",
        context={},
    )


@router.get(
    "/profile",
    name="CompanyProfilePage",
    dependencies=[Depends(require_page_permissions(["companies.read"]))],
)
async def get_company_profile_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/companies/profile.html",
        context={},
    )
