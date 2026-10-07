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
"""

from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.routers_api.activityexplorer import dao
from app.routers_api.mileage.read import millas_oficiales
from app.routers_api.activityexplorer.schemas import (
    ExplorerActivity,
    ExplorerGroup,
    ExplorerRange,
    ExplorerSummary,
    ExplorerSupervisor,
    ExplorerView,
)
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.users.permissions import require_permissions

router = APIRouter(prefix="/activity-explorer", tags=["Route · Activity Explorer"])


@router.get("", response_model=ExplorerView)
async def explorar(
    rango: ExplorerRange = Query("day", alias="range"),
    ancla: Optional[Date] = Query(None, alias="date"),
    supervisor_user_id: Optional[int] = Query(None),
    _authz: None = Depends(require_permissions(["route.activity.read"])),
    company: TenantContext = Depends(get_company_required),
) -> ExplorerView:
    """Un nivel del explorador para un supervisor y un periodo.

    `company` sale del subdominio y nunca del cliente. El supervisor pedido se
    **valida contra el conjunto autorizado**: uno de otra compañía no da 403
    sino 404, porque confirmar que existe ya sería decir algo de otro tenant.
    """
    autorizados = await dao.supervisores(company.id)
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

    hoy = await dao.business_day_actual(company.id)
    inicio, fin = dao.periodo(rango, ancla or hoy)

    opciones = [ExplorerSupervisor(**s) for s in autorizados]

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
            company_id=company.id, user_id=elegido, dia=inicio
        )
        por_dia = await dao.agregados_por_dia(
            company_id=company.id, user_id=elegido, inicio=inicio, fin=fin
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
                activities=len(paradas),
            ),
            activities=[ExplorerActivity(**p) for p in paradas],
        )

    por_dia = await dao.agregados_por_dia(
        company_id=company.id, user_id=elegido, inicio=inicio, fin=fin
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
