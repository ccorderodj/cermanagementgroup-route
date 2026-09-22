"""
API de las listas configurables por el administrador del tenant.

El código de lista viaja en la ruta y lo valida el enum: una lista inventada
no llega al DAO, la rechaza FastAPI con 422. Las ocho son producto; los valores
de dentro, del tenant.
"""

from fastapi import APIRouter, Depends, Query

from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.standardvalues.dao import StandardValuesDAO
from app.routers_api.standardvalues.models import StandardValueList
from app.routers_api.standardvalues.schemas import (
    StandardValueCreate,
    StandardValueListSummary,
    StandardValueRead,
    StandardValueReorder,
    StandardValueUpdate,
)
from app.routers_api.standardvalues.service import LIST_LABELS, StandardValueService
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/standard-values", tags=["Route · Standard values"])


@router.get("/lists")
async def get_lists(
    _authz: None = Depends(require_permissions(["route.standardvalues.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> list[StandardValueListSummary]:
    """Las ocho listas aprobadas, con cuántos valores activos tiene cada una."""
    totales = await StandardValuesDAO.counts_by_list(company_id=company.id)
    return [
        StandardValueListSummary(
            code=codigo.value,
            label=LIST_LABELS[codigo.value],
            active_values=totales.get(codigo.value, 0),
        )
        for codigo in StandardValueList
    ]


@router.get("/{list_code}")
async def get_values(
    list_code: StandardValueList,
    include_inactive: bool = Query(
        False,
        description=(
            "Incluye los valores retirados. Un administrador los necesita para "
            "reactivarlos o para leer un informe antiguo; un formulario "
            "operativo, no."
        ),
    ),
    _authz: None = Depends(require_permissions(["route.standardvalues.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> list[StandardValueRead]:
    filas = await StandardValuesDAO.list_for_code(
        company_id=company.id,
        list_code=list_code.value,
        include_inactive=include_inactive,
    )
    return [StandardValueRead.model_validate(fila) for fila in filas]


@router.post("")
async def create_value(
    payload: StandardValueCreate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.standardvalues.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> StandardValueRead:
    valor = await StandardValueService.create(
        company_id=company.id,
        actor_user_id=current_user.id,
        list_code=payload.list_code.value,
        label=payload.label,
        sort_order=payload.sort_order,
    )
    return StandardValueRead.model_validate(valor)


@router.put("/{value_id}")
async def update_value(
    value_id: int,
    payload: StandardValueUpdate,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.standardvalues.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> StandardValueRead:
    datos = payload.model_dump(exclude_unset=True)
    version = datos.pop("version", None)
    valor = await StandardValueService.update(
        company_id=company.id,
        value_id=value_id,
        actor_user_id=current_user.id,
        values=datos,
        expected_version=version,
    )
    return StandardValueRead.model_validate(valor)


@router.post("/{list_code}/reorder")
async def reorder_values(
    list_code: StandardValueList,
    payload: StandardValueReorder,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["route.standardvalues.manage"])),
    company: TenantContext = Depends(get_company_required),
) -> list[StandardValueRead]:
    filas = await StandardValueService.reorder(
        company_id=company.id,
        list_code=list_code.value,
        actor_user_id=current_user.id,
        value_ids=payload.value_ids,
    )
    return [StandardValueRead.model_validate(fila) for fila in filas]
