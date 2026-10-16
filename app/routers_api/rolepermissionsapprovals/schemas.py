from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.core import schema


class RolePermissionChangeRequestUserRead(BaseModel):
    user_id: int = Field(validation_alias="id")
    username: str
    first_name: str
    last_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class RolePermissionChangeRequestRead(BaseModel):
    id: int
    role_id: int
    role_name: Optional[str] = None
    role_category: Optional[str] = None
    requested_by_user_id: int
    reviewed_by_user_id: Optional[int] = None
    requested_by_user: RolePermissionChangeRequestUserRead
    reviewed_by_user: Optional[RolePermissionChangeRequestUserRead] = None
    status: str
    is_active: bool
    review_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Conceder y revocar son dos actividades distintas, así que se entregan
    # por separado en vez de un único "cambio".
    to_grant: list[str] = []
    to_revoke: list[str] = []

    # Si quien consulta puede revisarla, y si no, por qué.
    can_review: bool = False
    cannot_review_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RolePermissionChangeRequestReject(BaseModel):
    """Motivo del rechazo. Opcional, pero recomendable para el solicitante."""

    review_note: Optional[str] = None


class RolePermissionChangeRequestPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        role_id: Optional[int] = Query(None, ge=1),
        requested_by_user_id: Optional[int] = Query(None, ge=1),
        reviewed_by_user_id: Optional[int] = Query(None, ge=1),
        is_active: Optional[bool] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.role_id = role_id
        self.requested_by_user_id = requested_by_user_id
        self.reviewed_by_user_id = reviewed_by_user_id
        self.is_active = is_active
