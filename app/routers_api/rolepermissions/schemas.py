from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.core import schema


class RolePermissionBase(BaseModel):
    role_id: int
    permission_id: int


class RolePermissionCreate(RolePermissionBase):
    pass


class RolePermissionUpdate(BaseModel):
    role_id: Optional[int] = None
    permission_id: Optional[int] = None
    is_active: Optional[bool] = None


class RolePermissionBulkReplace(BaseModel):
    permission_ids: list[int]


class RolePermissionRead(RolePermissionBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RolePermissionChangeRequestRead(BaseModel):
    id: int
    role_id: int
    requested_by_user_id: int
    reviewed_by_user_id: Optional[int] = None
    is_active: bool
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RolePermissionPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        role_id: Optional[int] = Query(None, ge=1),
        permission_id: Optional[int] = Query(None, ge=1),
        is_active: Optional[bool] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.role_id = role_id
        self.permission_id = permission_id
        self.is_active = is_active
