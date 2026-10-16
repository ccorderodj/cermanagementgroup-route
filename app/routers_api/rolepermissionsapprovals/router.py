"""
Revisión de cambios de capacidades (el lado *checker* del maker-checker).

Aquí es donde una solicitud creada desde Roles & Permissions se aprueba o se
rechaza. Hasta ese momento el cambio no existe: `role_permission` no se toca.

Todo está acotado a la compañía activa. El listado ya no muestra las solicitudes
de otros tenants, y aprobar o rechazar por id una que no sea de esta compañía
devuelve 404 (AUD-SEC-007).
"""

from fastapi import APIRouter, Depends, Request

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.rolepermissionsapprovals.dao import RolePermissionChangeRequestsDAO
from app.routers_api.rolepermissionsapprovals.schemas import (
    RolePermissionChangeRequestPaginationParams,
    RolePermissionChangeRequestRead,
    RolePermissionChangeRequestReject,
)
from app.routers_api.rolepermissionsapprovals.service import RolePermissionApprovalService
from app.routers_api.users.dependencies import get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/rolepermissionsapprovals", tags=["Permission Requests"])


async def _to_read(
    row,
    *,
    viewer_id: int,
    company_id: int,
    viewer_has_authority: bool,
) -> RolePermissionChangeRequestRead:
    """Completa la solicitud con el rol, su diferencia y si el lector puede revisarla.

    `viewer_has_authority` llega ya resuelto desde el llamador: antes se
    consultaba una vez **por fila**, abriendo una sesión cada vez para un dato
    que es el mismo en toda la página (AUD-BE-028).
    """
    item = RolePermissionChangeRequestRead.model_validate(row)
    role = getattr(row, "role", None)
    item.role_name = getattr(role, "name", None)
    item.role_category = getattr(role, "category", None)

    diff = await RolePermissionApprovalService.diff_for_request(row)
    item.to_grant = diff["to_grant"]
    item.to_revoke = diff["to_revoke"]

    item.can_review = (
        item.status == "pending"
        and viewer_has_authority
        and row.requested_by_user_id != viewer_id
    )
    item.cannot_review_reason = None
    if item.status == "pending" and not item.can_review:
        if row.requested_by_user_id == viewer_id:
            item.cannot_review_reason = "You submitted this request"
        elif not viewer_has_authority:
            item.cannot_review_reason = "Only management roles can review"

    return item


@router.get("/pagination")
async def get_role_permission_change_requests_pagination(
    request: Request,
    params: RolePermissionChangeRequestPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["rolepermissionsapprovals.read"])),
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[RolePermissionChangeRequestRead]:
    page = await RolePermissionChangeRequestsDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=company.id,
        role_id=params.role_id,
        requested_by_user_id=params.requested_by_user_id,
        reviewed_by_user_id=params.reviewed_by_user_id,
        is_active=params.is_active,
    )

    # Una sola vez para toda la página, no una por fila.
    viewer_has_authority = await RolePermissionApprovalService.can_review(
        user_id=current_user.id,
        company_id=company.id,
    )

    items = [
        await _to_read(
            row,
            viewer_id=current_user.id,
            company_id=company.id,
            viewer_has_authority=viewer_has_authority,
        )
        for row in page.items
    ]

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=items,
        request=request,
    )
    return schema.PaginatedResponse[RolePermissionChangeRequestRead](
        **paginator.to_response()
    )


@router.post("/{request_id}/approve")
async def approve_request(
    request_id: int,
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
    _authz: None = Depends(require_permissions(["rolepermissions.update"])),
) -> RolePermissionChangeRequestRead:
    """Aplica el cambio. Requiere rol de gestión y no ser el solicitante."""
    updated = await RolePermissionApprovalService.approve(
        request_id=request_id,
        reviewer_user_id=current_user.id,
        company_id=company.id,
    )
    return await _to_read(
        updated,
        viewer_id=current_user.id,
        company_id=company.id,
        viewer_has_authority=True,
    )


@router.post("/{request_id}/reject")
async def reject_request(
    request_id: int,
    payload: RolePermissionChangeRequestReject,
    current_user: Users = Depends(get_current_user),
    company: TenantContext = Depends(get_company_required),
    _authz: None = Depends(require_permissions(["rolepermissions.update"])),
) -> RolePermissionChangeRequestRead:
    """Descarta el cambio sin aplicarlo. Requiere rol de gestión."""
    updated = await RolePermissionApprovalService.reject(
        request_id=request_id,
        reviewer_user_id=current_user.id,
        company_id=company.id,
        note=payload.review_note,
    )
    return await _to_read(
        updated,
        viewer_id=current_user.id,
        company_id=company.id,
        viewer_has_authority=True,
    )
