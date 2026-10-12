"""
API de Reports (RTE09).

* `GET /api/reports` — la vista del V0.7: `route.reports.read`.
* `GET /api/reports/export` — el Excel: `route.reports.read` **y**
  `route.reports.export`. Exportar es leer lo mismo en otro formato, así que
  quien no puede leer no puede exportar.

La compañía sale del subdominio y el supervisor pedido se valida contra el
conjunto autorizado del servidor: uno de otra compañía, o que ya no es
supervisor, recibe **404** —no 403—, porque confirmar que existe ya sería decir
algo. El periodo lo resuelve el servidor; el cliente no manda fechas de corte.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.routers_api.activityexplorer.dao import supervisores
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.reports import excel, service
from app.routers_api.reports.schemas import ReportRange, ReportView
from app.routers_api.users.permissions import require_permissions

router = APIRouter(prefix="/reports", tags=["Route · Reports"])

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _supervisor_autorizado(
    company_id: int, supervisor_user_id: Optional[int]
) -> tuple[Optional[int], str]:
    """El supervisor pedido, si es de los autorizados; `None` es *All*."""
    if supervisor_user_id is None:
        return None, "All Supervisors"
    for s in await supervisores(company_id):
        if s["user_id"] == supervisor_user_id:
            return supervisor_user_id, s["name"]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supervisor not found.")


@router.get("", response_model=ReportView)
async def ver_informe(
    rango: ReportRange = Query("week", alias="range"),
    ancla: Optional[Date] = Query(None, alias="date"),
    supervisor_user_id: Optional[int] = Query(None),
    grupo: Optional[Date] = Query(None, alias="group"),
    _authz: None = Depends(require_permissions(["route.reports.read"])),
    company: TenantContext = Depends(get_company_required),
) -> ReportView:
    """El informe consolidado de un periodo, para uno o todos.

    Sin `date`, el periodo en curso que decide el servidor. `group` —el inicio
    de un día, semana o mes del periodo— acota **sólo** el desglose.
    """
    elegido, _ = await _supervisor_autorizado(company.id, supervisor_user_id)
    try:
        vista, _filas = await service.construir(
            company_id=company.id,
            rango=rango,
            ancla=ancla,
            supervisor_user_id=elegido,
            grupo=grupo,
        )
    except service.GrupoFueraDelPeriodo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The group is not a day, week or month of the selected period.",
        )
    return ReportView(**vista)


@router.get("/export")
async def exportar_informe(
    rango: ReportRange = Query("week", alias="range"),
    ancla: Optional[Date] = Query(None, alias="date"),
    supervisor_user_id: Optional[int] = Query(None),
    _authz: None = Depends(
        require_permissions(["route.reports.read", "route.reports.export"])
    ),
    company: TenantContext = Depends(get_company_required),
) -> Response:
    """El mismo informe, en `.xlsx`: mismas filas, mismo filtro, mismo periodo.

    No acepta `group`: el subgrupo de la pantalla es una exploración del
    desglose, no un alcance de exportación (RTE09 E01 §19).
    """
    elegido, nombre = await _supervisor_autorizado(company.id, supervisor_user_id)
    vista, filas = await service.construir(
        company_id=company.id, rango=rango, ancla=ancla, supervisor_user_id=elegido
    )
    contenido = excel.libro(vista=vista, filas=filas, supervisor=nombre)
    etiqueta = nombre.replace(" ", "_")
    archivo = f"CER_Route_Report_{etiqueta}_{vista['start'].isoformat()}_{vista['end'].isoformat()}.xlsx"
    return Response(
        content=contenido,
        media_type=TIPO_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{archivo}"'},
    )
