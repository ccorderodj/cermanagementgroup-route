from datetime import datetime
from typing import List, Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.core import schema


class RegionBase(BaseModel):
    name: str


class RegionRead(RegionBase):
    id: int
    # `code` se expone también aquí. Antes solo lo traía `OperatingStateRead`,
    # así que el mismo estado llegaba al frontend con dos formas distintas
    # según el endpoint (AUD-BE-036).
    code: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperatingStateRead(BaseModel):
    """Un estado donde opera la compañía, con su marca de sede principal."""

    id: int
    code: str
    name: str
    is_main: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperatingStateCatalogItem(BaseModel):
    """Un estado del catálogo de EE.UU., marcando si la compañía opera en él."""

    id: int
    code: str
    name: str
    enabled: bool


class OperatingStatesUpdate(BaseModel):
    state_ids: List[int] = []


class OperatingStateMainUpdate(BaseModel):
    state_id: int


class RegionsPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        name: Optional[str] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.name = (name or "").strip() or None
