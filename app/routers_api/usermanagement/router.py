"""
Gestión de usuarios de la compañía activa.

Un usuario y su rol en la compañía son **un solo concepto** desde el punto de
vista de quien administra: `user_company` es una tabla puente, un detalle de
normalización, no algo que deba administrarse por separado. Por eso este módulo
expone una sola familia de endpoints —siempre con alcance de la compañía
activa— y resuelve el join aquí, en vez de obligar al frontend a cruzar dos
listados.

Dos límites que este módulo no puede cruzar:

* **No concede privilegio de plataforma.** `is_superuser` no está en ningún
  schema de entrada (D6, AUD-SEC-012).
* **No desactiva identidades.** Suspender actúa sobre la pertenencia a esta
  compañía; la identidad global es administración de plataforma (D7).
"""

from fastapi import APIRouter, Depends, Request

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.usermanagement.dao import UserManagementDAO
from app.routers_api.usermanagement.schemas import (
    UserAccessUpdate,
    UserManagementCreate,
    UserManagementRead,
    UserManagementUpdate,
    UsersPaginationParams,
)
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("/pagination")
async def get_users_pagination(
    request: Request,
    params: UsersPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["users.read"])),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[UserManagementRead]:
    """Usuarios de la compañía activa, ya con su rol resuelto."""
    page = await UserManagementDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=company.id,
        q=params.q,
        is_active=params.is_active,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=[UserManagementRead.model_validate(row) for row in page.items],
        request=request,
    )
    return schema.PaginatedResponse[UserManagementRead](**paginator.to_response())


@router.post("")
async def create_user(
    payload: UserManagementCreate,
    _authz: None = Depends(require_permissions(["users.create"])),
    company: TenantContext = Depends(get_company_required),
) -> UserManagementRead:
    """Crea el usuario y su pertenencia a la compañía en una sola operación."""
    created = await UserManagementDAO.create_user_with_company_role(
        company_id=company.id,
        **payload.model_dump(),
    )
    return UserManagementRead.model_validate(created)


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    payload: UserManagementUpdate,
    _authz: None = Depends(require_permissions(["users.update"])),
    company: TenantContext = Depends(get_company_required),
) -> UserManagementRead:
    """Actualiza los datos del usuario y, si viene, su rol en la compañía."""
    data = payload.model_dump(exclude_unset=True)

    updated = await UserManagementDAO.update_user_in_company(
        user_id=user_id,
        company_id=company.id,
        role_id=data.pop("role_id", None),
        password=data.pop("password", None),
        **data,
    )
    return UserManagementRead.model_validate(updated)


@router.put("/{user_id}/access")
async def set_user_access(
    user_id: int,
    payload: UserAccessUpdate,
    _authz: None = Depends(require_permissions(["users.update"])),
    company: TenantContext = Depends(get_company_required),
) -> UserManagementRead:
    """Activa o suspende el acceso del usuario **a esta compañía**.

    El usuario sigue existiendo en la plataforma y puede seguir entrando a otros
    tenants donde su pertenencia siga activa.
    """
    updated = await UserManagementDAO.set_membership_access(
        user_id=user_id,
        company_id=company.id,
        is_active=payload.is_active,
    )
    return UserManagementRead.model_validate(updated)
