from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.core import schema


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    # 'management' puede aprobar cambios de permisos; 'operative' solo pedirlos.
    category: str = "operative"


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RoleRead(RoleBase):
    id: int
    is_active: bool
    # Resuelto en el backend desde role_permission: para quien administra, el
    # número de permisos es una propiedad del rol.
    permission_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RolesPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        name: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.name = self._parse_name(name)
        self.is_active = is_active

    def _parse_name(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        value = raw.strip()
        return value or None


class RolePermissionCatalogItem(BaseModel):
    """Un permiso del catálogo, indicando si el rol lo tiene concedido."""

    id: int
    name: str
    description: Optional[str] = None
    module: str
    action: str
    granted: bool


class RolePermissionsReplace(BaseModel):
    """Conjunto completo de permisos del rol (reemplaza el anterior)."""

    permission_ids: list[int]


class RolePermissionPendingRequest(BaseModel):
    """Solicitud de cambio de permisos esperando revisión de otro admin."""

    id: int
    role_id: int
    requested_by_user_id: Optional[int] = None
    created_at: datetime

    # Conceder y revocar se presentan por separado.
    to_grant: list[str] = []
    to_revoke: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class RolePermissionsView(BaseModel):
    """Permisos del rol + si hay un cambio pendiente de aprobación."""

    permissions: list[RolePermissionCatalogItem]
    pending_request: Optional[RolePermissionPendingRequest] = None
