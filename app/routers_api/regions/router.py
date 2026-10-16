"""
Estados de EE.UU. en los que opera la compañía.

`region` es un catálogo global; lo que este módulo expone es siempre el
subconjunto del tenant activo. **Ningún endpoint de aquí es público**: antes
tres de ellos se servían sin sesión a través del router público y devolvían los
estados de operación y la sede principal de la compañía a cualquiera que
conociera el subdominio (AUD-SEC-002).
"""

from fastapi import APIRouter, Depends, Request
from pydantic import TypeAdapter

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.regions.dao import RegionsDAO
from app.routers_api.regions.schemas import (
    OperatingStateCatalogItem,
    OperatingStateMainUpdate,
    OperatingStateRead,
    OperatingStatesUpdate,
    RegionRead,
    RegionsPaginationParams,
)
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/regions", tags=["Regions"])


@router.get("")
async def get_regions(
    _authz: None = Depends(require_permissions(["regions.read"])),
    current_company: TenantContext = Depends(get_company_required),
) -> list[RegionRead]:
    regions = await RegionsDAO.find_all_by_company(company_id=current_company.id)
    return TypeAdapter(list[RegionRead]).validate_python(regions)


@router.get("/operating")
async def get_operating_states(
    _authz: None = Depends(require_permissions(["regions.read"])),
    current_company: TenantContext = Depends(get_company_required),
) -> list[OperatingStateRead]:
    """Estados donde opera la compañía activa, con la sede principal primero."""
    rows = await RegionsDAO.find_operating_states(company_id=current_company.id)
    return TypeAdapter(list[OperatingStateRead]).validate_python(rows)


@router.get("/catalog")
async def get_operating_states_catalog(
    _authz: None = Depends(require_permissions(["regions.read"])),
    current_company: TenantContext = Depends(get_company_required),
) -> list[OperatingStateCatalogItem]:
    """Catálogo completo de estados de EE.UU., marcando cuáles opera la compañía."""
    rows = await RegionsDAO.find_catalog_by_company(company_id=current_company.id)
    return TypeAdapter(list[OperatingStateCatalogItem]).validate_python(rows)


@router.put("/operating")
async def update_operating_states(
    payload: OperatingStatesUpdate,
    _authz: None = Depends(require_permissions(["regions.update"])),
    current_company: TenantContext = Depends(get_company_required),
) -> list[OperatingStateRead]:
    """Reemplaza el conjunto de estados donde opera la compañía."""
    await RegionsDAO.sync_operating_states(
        company_id=current_company.id,
        state_ids=payload.state_ids,
    )
    rows = await RegionsDAO.find_operating_states(company_id=current_company.id)
    return TypeAdapter(list[OperatingStateRead]).validate_python(rows)


@router.put("/operating/main")
async def update_operating_states_main(
    payload: OperatingStateMainUpdate,
    _authz: None = Depends(require_permissions(["regions.update"])),
    current_company: TenantContext = Depends(get_company_required),
) -> list[OperatingStateRead]:
    """Marca un estado activo como la sede principal."""
    await RegionsDAO.set_main_state(
        company_id=current_company.id,
        state_id=payload.state_id,
    )
    rows = await RegionsDAO.find_operating_states(company_id=current_company.id)
    return TypeAdapter(list[OperatingStateRead]).validate_python(rows)


@router.get("/pagination")
async def get_pagination(
    request: Request,
    params: RegionsPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["regions.read"])),
    current_company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[RegionRead]:
    page = await RegionsDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=current_company.id,
        name=params.name,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=[RegionRead.model_validate(row) for row in page.items],
        request=request,
    )
    return schema.PaginatedResponse[RegionRead](**paginator.to_response())
