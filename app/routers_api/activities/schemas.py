"""Contratos de la ejecución tras la llegada."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.routers_api.activities.models import TerminalAction


class ActivityStart(BaseModel):
    """Arrancar el bloque de la parada.

    `activity_ids` es obligatorio donde el contexto tiene lista —Client Visit,
    Recruiting, Other— y debe venir vacío donde no la tiene. El servidor lo
    comprueba contra el propósito del viaje: no se acepta "por si acaso".
    """

    model_config = ConfigDict(extra="forbid")

    activity_ids: list[int] = Field(default_factory=list, max_length=20)

    #: Evidencia de tiempo del dispositivo, con la semántica de RTE03 (D-10).
    device_captured_at: Optional[datetime] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class ActivityTerminalize(BaseModel):
    """Terminar o marcharse. Las dos exigen resultado.

    `outcome_id` no es opcional en ninguno de los dos caminos: es la decisión
    PD-02 y FR-10, y por eso no hay un valor por defecto que rellenar.
    """

    model_config = ConfigDict(extra="forbid")

    action: TerminalAction
    outcome_id: int
    #: Opcional siempre. No sustituye a un dato estructurado que falte.
    notes: Optional[str] = Field(default=None, max_length=2000)
    #: Sólo Check Delivery, y allí obligatorio.
    received_by_id: Optional[int] = None

    device_captured_at: Optional[datetime] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class SelectedActivityRead(BaseModel):
    """Una actividad del bloque, con la etiqueta que tenía al elegirse."""

    model_config = ConfigDict(from_attributes=True)

    standard_value_id: int
    label: str
    sort_order: int


class ActivityExecutionRead(BaseModel):
    """El bloque, tal como lo lee el cliente.

    Las etiquetas viajan junto a las referencias porque el histórico tiene que
    poder leerse aunque la lista haya cambiado después.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    work_session_id: int
    trip_id: int
    status: str
    terminal_action: Optional[str] = None

    started_at: datetime
    started_received_at: datetime
    started_at_source: str
    ended_at: Optional[datetime] = None
    ended_received_at: Optional[datetime] = None
    ended_at_source: Optional[str] = None

    outcome_standard_value_id: Optional[int] = None
    outcome_label: Optional[str] = None
    received_by_standard_value_id: Optional[int] = None
    received_by_label: Optional[str] = None
    notes: Optional[str] = None

    activities: list[SelectedActivityRead] = []
    version: int
