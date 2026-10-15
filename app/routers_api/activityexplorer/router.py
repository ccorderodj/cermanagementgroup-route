"""
API del Activity Explorer.

Un endpoint, un nivel
----------------------
La pantalla aprobada tiene tres estados y nada más: qué supervisor, qué fecha y
qué rango. Este endpoint recibe exactamente eso y devuelve el nivel
correspondiente, con sus grupos o con sus paradas. No hay un endpoint por
nivel porque no hay tres contratos: hay uno con cuatro profundidades, y partirlo
obligaría al navegador a saber qué agrupa cada rango — que es una regla de
producto, no una decisión de pantalla.

Quién puede leer esto
----------------------
`route.activity.read`, comprobado en el servidor. Es historia de **toda la
compañía**: un supervisor ve sus propias paradas en su móvil y no las de los
demás, así que esta capacidad no está en su rol. Adivinar la URL no sirve de
nada, que es lo que §9 exige comprobar.

Y el alcance lo decide el servidor
-----------------------------------
Las opciones del selector de supervisor salen de aquí, no de una lista que el
navegador filtre. Cuando exista jerarquía organizativa será este modelo de
lectura el que estreche el conjunto, sin que la pantalla cambie.

La actividad propia: `/me` (RTE08 personal)
-------------------------------------------
El supervisor consulta **su** historia en `/route/activity`. No usa el endpoint
de arriba: aquél exige `route.activity.read`, que es historia de toda la
compañía, y dársela al supervisor ampliaría su alcance. `/me` exige
`route.worksession.execute` —la capacidad con la que ya ejecuta su jornada y
entra al shell— y el sujeto **no es un parámetro**: es el usuario de la sesión,
en el tenant del subdominio. Un `supervisor_user_id`, `user_id` o `company_id`
en la petición no forma parte del contrato y se ignora. Tampoco devuelve el
directorio de supervisores.

Las dos rutas construyen la vista con la misma función (`_vista`): mismas
consultas, mismas reglas (R-1, H-2), mismos números.
"""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.routers_api.activityexplorer import dao
from app.routers_api.activityexplorer import route_map
from app.routers_api.mileage.read import millas_oficiales
from app.routers_api.activityexplorer.schemas import (
    ExplorerActivity,
    ExplorerGroup,
    ExplorerRange,
    ExplorerSummary,
    ExplorerSupervisor,
    ExplorerView,
    TripMapPoint,
    TripMapRead,
    TripMapTiles,
)
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.organization.scope import (
    alcance_administrativo,
    condicion_de_jornadas,
)
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.worksessions.models import WorkSession
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions

router = APIRouter(prefix="/activity-explorer", tags=["Route · Activity Explorer"])


@router.get("", response_model=ExplorerView)
async def explorar(
    rango: ExplorerRange = Query("day", alias="range"),
    ancla: Optional[Date] = Query(None, alias="date"),
    supervisor_user_id: Optional[int] = Query(None),
    _authz: None = Depends(require_permissions(["route.activity.read"])),
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
) -> ExplorerView:
    """Un nivel del explorador para un supervisor y un periodo.

    `company` sale del subdominio y nunca del cliente. El supervisor pedido se
    **valida contra el conjunto autorizado**: uno de otra compañía no da 403
    sino 404, porque confirmar que existe ya sería decir algo de otro tenant.

    Un `route_manager` sólo tiene en el conjunto a quienes estuvieron en su
    rama, y de cada uno sólo las jornadas que empezaron mientras lo estaban
    (`organization.scope`).
    """
    alcance = await alcance_administrativo(company_id=company.id, actor_user_id=current_user.id)
    autorizados = [
        s for s in await dao.supervisores(company.id) if alcance.ve(s["user_id"])
    ]
    por_id = {s["user_id"]: s for s in autorizados}

    elegido: Optional[int]
    if supervisor_user_id is not None:
        if supervisor_user_id not in por_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found.",
            )
        elegido = supervisor_user_id
    else:
        # Como la línea base: el primero de la lista queda seleccionado.
        elegido = autorizados[0]["user_id"] if autorizados else None

    return await _vista(
        company_id=company.id,
        rango=rango,
        ancla=ancla,
        user_id=elegido,
        opciones=[ExplorerSupervisor(**s) for s in autorizados],
        jornadas=(
            None
            if elegido is None
            else condicion_de_jornadas(
                alcance, WorkSession.user_id, WorkSession.started_at, {elegido}
            )
        ),
    )


@router.get("/me", response_model=ExplorerView)
async def explorar_lo_propio(
    rango: ExplorerRange = Query("day", alias="range"),
    ancla: Optional[Date] = Query(None, alias="date"),
    _authz: None = Depends(require_permissions(["route.worksession.execute"])),
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
) -> ExplorerView:
    """La actividad **propia** del usuario de la sesión, en este tenant.

    El sujeto sale de la sesión y la compañía del subdominio; no hay parámetro
    que los cambie. Sin directorio: `supervisors` va vacío.
    """
    return await _vista(
        company_id=company.id,
        rango=rango,
        ancla=ancla,
        user_id=current_user.id,
        opciones=[],
    )


async def _vista(
    *,
    company_id: int,
    rango: str,
    ancla: Optional[Date],
    user_id: Optional[int],
    opciones: list[ExplorerSupervisor],
    jornadas=None,
) -> ExplorerView:
    """Un nivel del explorador para **una** persona ya autorizada.

    Quien llama decide el sujeto y lo ha validado: el administrador contra el
    conjunto de supervisores elegibles; `/me`, con la sesión.
    """
    elegido = user_id
    hoy = await dao.dia_actual_de(company_id, elegido)
    inicio, fin = dao.periodo(rango, ancla or hoy)

    if elegido is None:
        # Una compañía sin supervisores es un estado, no un error. Y no se
        # inventan grupos para que la pantalla tenga algo que dibujar.
        return ExplorerView(
            range=rango,
            start=inicio,
            end=fin,
            grouped_by=dao.AGRUPA_POR.get(rango),
            supervisors=opciones,
            supervisor_user_id=None,
            groups=[],
            summary=None,
            activities=[],
        )

    if rango == "day":
        paradas = await dao.paradas_del_dia(
            company_id=company_id, user_id=elegido, dia=inicio, jornadas=jornadas
        )
        por_dia = await dao.agregados_por_dia(
            company_id=company_id, user_id=elegido, inicio=inicio, fin=fin,
            jornadas=jornadas,
        )
        datos = por_dia.get(inicio)
        return ExplorerView(
            range=rango,
            start=inicio,
            end=fin,
            grouped_by=None,
            supervisors=opciones,
            supervisor_user_id=elegido,
            groups=[],
            summary=ExplorerSummary(
                official_miles=millas_oficiales(datos["metros"] if datos else None),
                mileage_pending=bool(datos and datos["pendientes"]),
                activity_seconds=datos["segundos"] if datos else 0,
                has_open_activity=bool(datos and datos["abiertos"]),
                # Paradas reales, **no filas de la lista** (R-1).
                #
                # Era `len(paradas)`, y mientras la lista contenía sólo
                # actividades las dos cosas coincidían. Desde que el detalle
                # incluye también los viajes sin parada, contar filas haría que
                # el número creciera con cada regreso a casa: diría «3
                # activities» donde hubo dos. El contador sigue respondiendo a
                # la misma pregunta que antes.
                activities=sum(1 for p in paradas if p["has_activity"]),
            ),
            activities=[ExplorerActivity(**p) for p in paradas],
        )

    por_dia = await dao.agregados_por_dia(
        company_id=company_id, user_id=elegido, inicio=inicio, fin=fin, jornadas=jornadas
    )
    grupos = dao.componer_grupos(rango, inicio, fin, por_dia)

    return ExplorerView(
        range=rango,
        start=inicio,
        end=fin,
        grouped_by=dao.AGRUPA_POR[rango],
        supervisors=opciones,
        supervisor_user_id=elegido,
        groups=[ExplorerGroup(**g) for g in grupos],
        summary=None,
        activities=[],
    )


@router.get("/trips/{trip_id}/map", response_model=TripMapRead)
async def mapa_del_viaje(
    trip_id: int,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(
        require_permissions(["route.activity.read", "route.activity.map.read"])
    ),
    company: TenantContext = Depends(get_company_required),
) -> TripMapRead:
    """Los puntos del cálculo de millas de **un** viaje, para el visor de ruta.

    Las dos capacidades a la vez: la de Activity y la del mapa, que ninguna
    plantilla concede. Después, el viaje tiene que estar en el alcance del
    actor —rama por periodo; Sales sólo para el CEO—: si no, 404, igual que un
    id que no existe.
    """
    alcance = await alcance_administrativo(company_id=company.id, actor_user_id=current_user.id)
    if not await route_map.viaje_en_alcance(company_id=company.id, trip_id=trip_id, alcance=alcance):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    puntos, proveedor = await route_map.puntos_del_calculo(company_id=company.id, trip_id=trip_id)
    return TripMapRead(
        trip_id=trip_id,
        available=bool(puntos),
        points=[TripMapPoint(**p) for p in puntos],
        provider=proveedor,
        tiles=TripMapTiles(url=settings.MAP_TILE_URL, attribution=settings.MAP_TILE_ATTRIBUTION),
    )
