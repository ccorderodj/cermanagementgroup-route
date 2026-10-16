"""Contratos de las listas configurables por el administrador."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.routers_api.standardvalues.models import StandardValueList


class StandardValueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    list_code: StandardValueList
    label: str = Field(min_length=1, max_length=120)
    #: Si no se envía, el valor se coloca al final de su lista.
    sort_order: Optional[int] = Field(default=None, ge=0)

    @field_validator("label")
    @classmethod
    def _limpiar(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("must not be blank")
        return limpio


class StandardValueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    sort_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    version: Optional[int] = None

    @field_validator("label")
    @classmethod
    def _limpiar(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        limpio = valor.strip()
        if not limpio:
            raise ValueError("must not be blank")
        return limpio


class StandardValueReorder(BaseModel):
    """Nuevo orden completo de una lista, de arriba abajo."""

    model_config = ConfigDict(extra="forbid")

    value_ids: list[int] = Field(min_length=1)


class StandardValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    list_code: str
    label: str
    sort_order: int
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class StandardValueListSummary(BaseModel):
    """Una de las ocho listas aprobadas, con cuántos valores activos tiene."""

    code: str
    label: str
    active_values: int
