from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.routers_api.locationcapture.models import INTERVALO_MAXIMO, INTERVALO_MINIMO

#: Tamaño máximo de un lote de muestras.
LOTE_MAXIMO = 50


class CaptureSettingRead(BaseModel):
    """La configuración de la compañía. `version=0`: nunca se guardó."""

    enabled: bool
    interval_seconds: int
    version: int
    updated_at: datetime | None
    updated_by_user_id: int | None
    min_interval_seconds: int = INTERVALO_MINIMO
    max_interval_seconds: int = INTERVALO_MAXIMO


class CaptureSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    interval_seconds: int = Field(ge=INTERVALO_MINIMO, le=INTERVALO_MAXIMO)
    #: La que se leyó; si otro guardó entre medias, 409.
    version: int = Field(ge=0)


class SampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_sample_id: UUID
    latitude: Decimal = Field(ge=-90, le=90, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, decimal_places=7)
    accuracy_m: Decimal = Field(ge=0, le=1_000_000)
    device_captured_at: datetime


class SamplesIn(BaseModel):
    """Un lote de una jornada. Ni usuario ni compañía: salen de la sesión."""

    model_config = ConfigDict(extra="forbid")

    work_session_id: int = Field(gt=0)
    samples: list[SampleIn] = Field(min_length=1, max_length=LOTE_MAXIMO)


class SampleResult(BaseModel):
    client_sample_id: UUID
    status: Literal["accepted", "duplicate", "rejected"]
    #: Código fijo cuando se rechaza: `future_timestamp`, `stale`,
    #: `outside_session`, `low_accuracy`.
    reason: str | None = None


class SamplesResult(BaseModel):
    results: list[SampleResult]
