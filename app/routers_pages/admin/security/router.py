"""
Pantallas de seguridad.

Cada ruta declara el permiso que exige. Sin el permiso no se sirve el HTML: se
devuelve 403 y el handler de la aplicacion de paginas lo renderiza como una
pantalla de acceso denegado (AUD-BE-001).
"""

from fastapi import APIRouter, Depends, Request

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates
from app.routers_pages.dependencies import require_page_permissions


router = APIRouter(
    prefix="/security",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get(
    "/users/list",
    name="SecurityUsersPage",
    dependencies=[Depends(require_page_permissions(["users.read"]))],
)
async def get_security_users_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/security/users/list.html",
        context={},
    )


@router.get(
    "/roles/list",
    name="SecurityRolesPage",
    dependencies=[Depends(require_page_permissions(["roles.read"]))],
)
async def get_security_roles_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/security/roles/list.html",
        context={},
    )


@router.get(
    "/permissions/list",
    name="SecurityPermissionsPage",
    dependencies=[Depends(require_page_permissions(["permissions.read"]))],
)
async def get_security_permissions_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/security/permissions/list.html",
        context={},
    )


@router.get(
    "/role-permission-requests/list",
    name="SecurityRolePermissionRequestsPage",
    dependencies=[Depends(require_page_permissions(["rolepermissionsapprovals.read"]))],
)
async def get_security_role_permission_requests_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/security/rolepermissionrequests/list.html",
        context={},
    )
