"""
Roles y las capacidades que conceden.

Un rol y su conjunto de capacidades son **un solo concepto** para quien
administra la seguridad. `role_permission` es una tabla puente, no una entidad
que deba mantenerse por separado, así que este módulo resuelve la relación aquí
y expone el rol ya con su catálogo.

Todo cuelga de la compañía activa: los roles son del tenant (D8), y ninguna
consulta de este módulo se hace sin `company_id`.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import TypeAdapter

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.rolepermissionsapprovals.service import RolePermissionApprovalService
from app.routers_api.roles.dao import RolesDAO
from app.routers_api.roles.schemas import (
    RoleCreate,
    RolePermissionCatalogItem,
    RolePermissionPendingRequest,
    RolePermissionsReplace,
    RolePermissionsView,
    RoleRead,
    RolesPaginationParams,
    RoleUpdate,
)
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/roles", tags=["Roles"])


async def _permissions_view(*, role_id: int, company_id: int) -> RolePermissionsView:
    """Catálogo del rol + la solicitud pendiente con su diferencia."""
    rows = await RolesDAO.permission_catalog_for_role(
        role_id=role_id,
        company_id=company_id,
    )
    pending = await RolePermissionApprovalService.pending_for_role(
        role_id=role_id,
        company_id=company_id,
    )

    pending_read = None
    if pending is not None:
        diff = await RolePermissionApprovalService.diff_for_request(pending)
        pending_read = RolePermissionPendingRequest.model_validate(pending)
        pending_read.to_grant = diff["to_grant"]
        pending_read.to_revoke = diff["to_revoke"]

    return RolePermissionsView(
        permissions=TypeAdapter(list[RolePermissionCatalogItem]).validate_python(rows),
        pending_request=pending_read,
    )


async def _with_permission_counts(rows) -> list[RoleRead]:
    items = [RoleRead.model_validate(row) for row in rows]
    counts = await RolesDAO.permission_counts([item.id for item in items])
    for item in items:
        item.permission_count = counts.get(item.id, 0)
    return items


@router.get("")
async def get_roles(
    _authz: None = Depends(require_permissions(["roles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[RoleRead]:
    rows = await RolesDAO.find_all_ordered(company_id=company.id)
    return await _with_permission_counts(rows)


@router.get("/pagination")
async def get_pagination(
    request: Request,
    params: RolesPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["roles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[RoleRead]:
    page = await RolesDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=company.id,
        name=params.name,
        is_active=params.is_active,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=await _with_permission_counts(page.items),
        request=request,
    )
    return schema.PaginatedResponse[RoleRead](**paginator.to_response())


@router.get("/{role_id}/permissions")
async def get_role_permissions(
    role_id: int,
    _authz: None = Depends(require_permissions(["roles.read"])),
    company: TenantContext = Depends(get_company_required),
) -> RolePermissionsView:
    """Capacidades del rol y si tiene un cambio pendiente de aprobar."""
    return await _permissions_view(role_id=role_id, company_id=company.id)


@router.put("/{role_id}/permissions")
async def replace_role_permissions(
    role_id: int,
    payload: RolePermissionsReplace,
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["rolepermissions.update"])),
    company: TenantContext = Depends(get_company_required),
) -> RolePermissionsView:
    """Envía el nuevo conjunto de capacidades **a aprobación**.

    No aplica el cambio: por segregación de deberes, las capacidades quedan como
    están hasta que **otro** administrador revise la solicitud desde Permission
    Requests. Quien la envía no puede aprobarla.
    """
    await RolePermissionApprovalService.submit(
        role_id=role_id,
        company_id=company.id,
        permission_ids=payload.permission_ids,
        requested_by_user_id=current_user.id,
    )
    return await _permissions_view(role_id=role_id, company_id=company.id)


@router.post("")
async def create_role(
    payload: RoleCreate,
    _authz: None = Depends(require_permissions(["roles.create"])),
    company: TenantContext = Depends(get_company_required),
) -> RoleRead:
    created = await RolesDAO.create(company_id=company.id, **payload.model_dump())
    return RoleRead.model_validate(created)


@router.put("/{role_id}")
async def update_role(
    role_id: int,
    payload: RoleUpdate,
    _authz: None = Depends(require_permissions(["roles.update"])),
    company: TenantContext = Depends(get_company_required),
) -> RoleRead:
    updated = await RolesDAO.update_for_company(
        role_id=role_id,
        company_id=company.id,
        **payload.model_dump(exclude_unset=True),
    )
    return RoleRead.model_validate(updated)


@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    _authz: None = Depends(require_permissions(["roles.delete"])),
    company: TenantContext = Depends(get_company_required),
) -> RoleRead:
    deleted = await RolesDAO.soft_delete(role_id=role_id, company_id=company.id)
    return RoleRead.model_validate(deleted)
