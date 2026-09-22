"""
Espacio de trabajo móvil del supervisor de CER Route.

Sólo exige **sesión**, no una capacidad. Es el mismo criterio que `ProfilePage`:
esta es la pantalla propia de quien entra, y lo que pueda *hacer* en ella se
autoriza en los endpoints que la alimenten cuando existan (RTE03+). Pedir aquí
`route.worksession.execute` obligaría a declarar esa capacidad antes de que
ningún endpoint la exija, y el catálogo rechaza —a propósito— las capacidades
que no protegen nada.

Estas tres rutas son **andamiaje de RTE02**: establecen el shell y su
navegación. No simulan jornada, viaje ni actividad, y las pantallas lo dicen
abiertamente en vez de enseñar una lista vacía que parezca una función
terminada (`AGENTS.md`: no simular lo que no está construido).
"""

from fastapi import APIRouter, Request

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates


router = APIRouter(
    prefix="/route",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get("", name="RouteMyRoutePage")
async def get_my_route_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="route/my-route.html",
        context={},
    )


@router.get("/activity", name="RouteActivityPage")
async def get_route_activity_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="route/activity.html",
        context={},
    )


@router.get("/me", name="RouteMePage")
async def get_route_me_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="route/me.html",
        context={},
    )
