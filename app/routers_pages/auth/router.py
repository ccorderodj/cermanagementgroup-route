from fastapi import APIRouter, Request

from app.core.utils.web_routers import (
    CheckNameRoute,
    CustomTemplates,
)

router = APIRouter(
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get("/login", name="LoginPage")
async def get_login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={},
    )


@router.get("/password-reset", name="PasswordResetPage")
async def get_password_reset_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="password-reset.html",
        context={},
    )


@router.get("/change-password", name="ChangePasswordPage")
async def get_change_password_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="change-password.html",
        context={},
    )


@router.get("/admin", name="AdminPage")
async def get_admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={},
    )