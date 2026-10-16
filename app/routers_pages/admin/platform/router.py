"""
Pantallas de plataforma: configuración y diagnóstico del despliegue.

**No son de tenant.** Lo que enseñan —el host del servidor de correo, la raíz
del almacén, qué integraciones faltan— pertenece al despliegue entero, así que
las protege `require_platform_admin_page` y no un permiso del catálogo. Ese
catálogo se concede *dentro* de una compañía (D6): un permiso ahí habría dejado
que el dueño de un tenant leyera la configuración de todos.

Es la misma decisión que ya tomó la pantalla de compañías, y por el mismo
motivo.

Settings configura y Diagnostics demuestra. Las dos leen la preparación para
producción de `app/core/platform/readiness.py`, la misma fuente, así que no
pueden contradecirse sobre si un gate está cerrado.
"""

from fastapi import APIRouter, Depends, Request

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates
from app.routers_pages.dependencies import require_platform_admin_page


router = APIRouter(
    prefix="/platform",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get(
    "/settings",
    name="PlatformSettingsPage",
    dependencies=[Depends(require_platform_admin_page())],
)
async def get_platform_settings_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/platform/settings.html",
        context={},
    )


@router.get(
    "/diagnostics",
    name="PlatformDiagnosticsPage",
    dependencies=[Depends(require_platform_admin_page())],
)
async def get_platform_diagnostics_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/platform/diagnostics.html",
        context={},
    )
