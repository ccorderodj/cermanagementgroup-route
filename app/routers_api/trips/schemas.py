"""Contratos del viaje.

Ningún schema de entrada acepta quién actúa, en qué compañía ni en qué jornada:
eso sale de la sesión autenticada y del subdominio. Lo único que el cliente
aporta es su intención —a qué va— y la evidencia de cuándo lo hizo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.routers_api.trips.models import TripPurpose


class TripPlan(BaseModel):
    """Lo que el supervisor decide antes de salir.

    `standard_value_id` sólo lo admiten los tres contextos que CER fijó como
    de pre-viaje (Employee Visit, Check Delivery, Office). En los demás el
    servidor lo rechaza con 422: lo que se elige al llegar es de RTE05.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: TripPurpose
    #: Texto libre por decisión de CER: destino, área, referencia, oficina.
    #: **No** es un catálogo y no se convierte en uno.
    context_reference: Optional[str] = Field(default=None, max_length=500)
    standard_value_id: Optional[int] = None

    #: Evidencia de tiempo del dispositivo, con la semántica de RTE03: cuándo
    #: lo pulsó el supervisor, que puede ser antes de que el servidor lo reciba.
    device_captured_at: Optional[datetime] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class TripTransition(BaseModel):
    """Cuerpo de una transición: sólo evidencia de tiempo."""

    model_config = ConfigDict(extra="forbid")

    device_captured_at: Optional[datetime] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class TripPurposeChangeRead(BaseModel):
    """Un cambio de plan, tal como quedó registrado."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    from_purpose: str
    from_context_reference: Optional[str] = None
    from_standard_value_id: Optional[int] = None
    to_purpose: str
    to_context_reference: Optional[str] = None
    to_standard_value_id: Optional[int] = None
    changed_at: datetime
    changed_by: int


class TripRead(BaseModel):
    """El viaje tal como lo lee el cliente.

    Lleva el plan **original** además del actual, a propósito: es lo que hace
    visible que el plan cambió por el camino sin tener que pedir el historial.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    work_session_id: int
    sequence: int
    status: str

    original_purpose: str
    original_context_reference: Optional[str] = None
    original_standard_value_id: Optional[int] = None

    current_purpose: str
    current_context_reference: Optional[str] = None
    current_standard_value_id: Optional[int] = None

    started_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    version: int
    created_at: datetime
    updated_at: datetime
