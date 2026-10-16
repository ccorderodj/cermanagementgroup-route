"""
Consulta de vínculos rol-capacidad.

Este módulo es de **solo lectura**. Cambiar las capacidades de un rol se hace
por `PUT /roles/{id}/permissions`, que crea una solicitud de aprobación, y se
resuelve en `/rolepermissionsapprovals`.

Antes existían aquí endpoints que escribían directamente
(`POST /rolepermissions`, `PUT /rolepermissions/{id}`, `.../activate-inactive`).
Se retiraron porque **esquivaban el maker-checker**: dejaban conceder o revocar
capacidades sin que nadie las revisara, que es justo lo que el control existe
para impedir. Un control que se puede rodear por otra puerta no es un control.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import TypeAdapter

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.rolepermissions.dao import RolePermissionsDAO
from app.routers_api.rolepermissions.schemas import (
    RolePermissionPaginationParams,
    RolePermissionRead,
)
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/rolepermissions", tags=["Role Permissions"])


@router.get("")
async def get_role_permissions(
    role_id: int | None = None,
    _authz: None = Depends(require_permissions(["rolepermissions.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[RolePermissionRead]:
    rows = await RolePermissionsDAO.find_all_ordered(
        company_id=company.id,
        role_id=role_id,
    )
    return TypeAdapter(list[RolePermissionRead]).validate_python(rows)


@router.get("/pagination")
async def get_pagination(
    request: Request,
    params: RolePermissionPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["rolepermissions.read"])),
    company: TenantContext = Depends(get_company_required),
) -> schema.PaginatedResponse[RolePermissionRead]:
    page = await RolePermissionsDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        company_id=company.id,
        role_id=params.role_id,
        permission_id=params.permission_id,
        is_active=params.is_active,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=TypeAdapter(list[RolePermissionRead]).validate_python(page.items),
        request=request,
    )
    return schema.PaginatedResponse[RolePermissionRead](**paginator.to_response())
