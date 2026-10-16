from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.core import schema


class PermissionBase(BaseModel):
    name: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PermissionRead(PermissionBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PermissionPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        name: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.name = name
        self.is_active = is_active


class PermissionRoleRef(BaseModel):
    """Un rol que tiene concedido este permiso."""

    name: str
    category: Optional[str] = None


class FeatureMapItem(BaseModel):
    """Una capacidad del sistema: módulo + acción, y quién la tiene."""

    id: int
    name: str
    description: Optional[str] = None
    module: str
    action: str
    is_active: bool
    roles: list[PermissionRoleRef] = []
