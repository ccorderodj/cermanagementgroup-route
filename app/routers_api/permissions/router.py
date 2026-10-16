"""
Catálogo de capacidades del sistema. **Solo lectura.**

Los endpoints de creación, edición y borrado se retiraron. Un permiso describe
algo que la aplicación sabe hacer: crear `inventario.exportar` desde una
pantalla no añade la funcionalidad, solo una fila que no hace nada y que además
puede concederse a un rol, dando la impresión de un privilegio inexistente
(§6 del encargo de remediación).

El catálogo lo define `app/core/rbac/catalog.py` y lo siembra el bootstrap.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import TypeAdapter

from app.core import schema
from app.core.utils.api_paginator import Paginator
from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.permissions.dao import PermissionsDAO
from app.routers_api.permissions.schemas import (
    FeatureMapItem,
    PermissionPaginationParams,
    PermissionRead,
)
from app.routers_api.users.permissions import require_permissions


router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get("/feature-map")
async def get_feature_map(
    _authz: None = Depends(require_permissions(["permissions.read"])),
    company: TenantContext = Depends(get_company_required),
) -> list[FeatureMapItem]:
    """Qué puede hacerse en el sistema y qué roles de esta compañía pueden hacerlo."""
    rows = await PermissionsDAO.feature_map(company_id=company.id)
    return TypeAdapter(list[FeatureMapItem]).validate_python(rows)


@router.get("")
async def get_permissions(
    _authz: None = Depends(require_permissions(["permissions.read"])),
) -> list[PermissionRead]:
    rows = await PermissionsDAO.find_all_ordered()
    return TypeAdapter(list[PermissionRead]).validate_python(rows)


@router.get("/pagination")
async def get_pagination(
    request: Request,
    params: PermissionPaginationParams = Depends(),
    _authz: None = Depends(require_permissions(["permissions.read"])),
) -> schema.PaginatedResponse[PermissionRead]:
    page = await PermissionsDAO.paginate(
        page=params.page,
        page_size=params.page_size,
        name=params.name,
        is_active=params.is_active,
    )

    paginator = Paginator(
        total_items=page.total,
        page=params.page,
        page_size=params.page_size,
        results=[PermissionRead.model_validate(row) for row in page.items],
        request=request,
    )
    return schema.PaginatedResponse[PermissionRead](**paginator.to_response())
