"""
Compañías.

Dos audiencias muy distintas conviven aquí y conviene no mezclarlas:

* **Perfil de la compañía activa** — lo administra el tenant. Exige los permisos
  `companies.read` / `companies.update` y actúa siempre sobre la compañía que
  resolvió el subdominio, nunca sobre un id que venga del cliente.

* **Listado de compañías** — es administración de plataforma. Devuelve todos los
  tenants, así que queda reservado a `Users.is_superuser` (D6). Antes bastaba
  con estar autenticado: cualquier usuario de cualquier compañía obtenía el
  listado completo de clientes (AUD-SEC-005).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import TypeAdapter

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dao import CompaniesDAO
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.schemas import (
    CompaniesPaginationParams,
    CompanyProfileResponse,
    CompanyProfileUpdate,
    CompanyRead,
)
from app.routers_api.users.dependencies import require_platform_admin
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/companies", tags=["Companies"])


# ── Administración de plataforma ────────────────────────────────────────────


@router.get("")
async def get_companies(
    _platform_admin: Users = Depends(require_platform_admin),
) -> list[CompanyRead]:
    """Todos los tenants de la plataforma. Solo administración de plataforma."""
    rows = await CompaniesDAO.find_all()
    return TypeAdapter(list[CompanyRead]).validate_python(rows)


@router.get("/pagination")
async def get_pagination(
    request: Request,
    params: CompaniesPaginationParams = Depends(),
    _platform_admin: Users = Depends(require_platform_admin),
) -> schema.PaginatedResponse[CompanyRead]:
    """Listado paginado de tenants. Solo administración de plataforma."""
    page = await CompaniesDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        name=params.name,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=[CompanyRead.model_validate(row) for row in page.items],
        request=request,
    )
    return schema.PaginatedResponse[CompanyRead](**paginator.to_response())


# ── Perfil de la compañía activa ────────────────────────────────────────────


@router.get("/profile", response_model=CompanyProfileResponse)
async def get_company_profile(
    _authz: None = Depends(require_permissions(["companies.read"])),
    current_company: TenantContext = Depends(get_company_required),
):
    """Perfil completo de la compañía activa.

    Se lee de la base en vez de servir el `TenantContext` de la petición: ese
    contexto solo lleva lo necesario para resolver el tenant y pintar la marca,
    no el perfil entero.
    """
    company = await CompaniesDAO.get_for_profile(current_company.id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    return CompanyProfileResponse.model_validate(company)


@router.put("/profile", response_model=CompanyProfileResponse)
async def update_company_profile(
    payload: CompanyProfileUpdate,
    _authz: None = Depends(require_permissions(["companies.update"])),
    current_company: TenantContext = Depends(get_company_required),
):
    """Datos de negocio y marca de la compañía activa.

    `subdomain` y `domain` NO se pueden tocar desde aquí: son la clave con la
    que se resuelve el tenant, y cambiarlos dejaba la compañía inalcanzable para
    todos sus usuarios, administradores incluidos (D5, AUD-SEC-004). Ese cambio
    pertenece al canal de administración de plataforma.
    """
    data = await CompaniesDAO.update_profile_by_company_id(
        company_id=current_company.id,
        data=payload.model_dump(),
    )
    return CompanyProfileResponse(**data)
