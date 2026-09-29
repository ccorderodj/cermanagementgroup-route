"""
Espacio de trabajo móvil del supervisor de CER Route.

Exige `route.worksession.execute`, la capacidad con la que se ejecuta la
jornada, el viaje y la parada.

Antes exigía **sólo sesión**, y el motivo era bueno en su momento: cuando se
escribió, esa capacidad no existía todavía y el catálogo rechaza —a propósito—
las capacidades que no protegen ningún endpoint. Ese motivo caducó en RTE03:
hoy la capacidad existe y protege toda la superficie operativa.

Dejarla sólo con sesión significaba que un usuario del núcleo —un `viewer`, un
`manager` sin rol de Route— abría el shell operativo y lo veía fallar en cada
llamada. No era un agujero de autorización, porque ningún endpoint servía nada
sin la capacidad, pero sí una pantalla que no puede funcionar para quien la
abre. La puerta se cierra donde corresponde (PD-10 del cierre 003).

No se añade ninguna capacidad: se exige la que ya existe.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.utils.web_routers import CheckNameRoute, CustomTemplates


def exige_ejecucion_de_ruta(request: Request) -> None:
    """La capacidad operativa, **también** para la plataforma.

    No usa `require_page_permissions` a propósito, y la diferencia es una sola
    línea de esa función: allí un superusuario de plataforma pasa sin
    comprobación. Para las pantallas de administración eso es correcto —quien
    opera el despliegue tiene que poder entrar a diagnosticar—, pero aquí no:
    FR-13 dice que la identidad de plataforma **por sí sola** no concede acceso
    operativo a Route, y una jornada la ejecuta una persona de una compañía, no
    el administrador del servidor.

    Es más estricta que la del núcleo, no más laxa, y no lo modifica: cambiar
    `require_page_permissions` afectaría a todas las páginas de administración
    del producto, que está fuera de este alcance.
    """
    usuario = getattr(request.state, "user", None)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    concedidas = getattr(request.state, "permissions", set()) or set()
    if "route.worksession.execute" not in concedidas:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this section.",
        )


#: La capacidad operativa. Una sola, y la misma en las tres pantallas del
#: shell: entrar al espacio de trabajo es entrar a ejecutar.
EJECUTA = [Depends(exige_ejecucion_de_ruta)]


router = APIRouter(
    prefix="/route",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

templates = CustomTemplates(directory="app/templates")


@router.get("", name="RouteMyRoutePage", dependencies=EJECUTA)
async def get_my_route_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="route/my-route.html",
        context={},
    )


@router.get("/activity", name="RouteActivityPage", dependencies=EJECUTA)
async def get_route_activity_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="route/activity.html",
        context={},
    )


@router.get("/me", name="RouteMePage", dependencies=EJECUTA)
async def get_route_me_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="route/me.html",
        context={},
    )
