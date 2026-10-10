"""Contratos de la evidencia de odómetro."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.routers_api.odometer.models import (
    OdometerEvidenceType,
    OdometerExceptionReason,
)


class OdometerReadingConfirm(BaseModel):
    """La lectura que el supervisor confirma. La autoridad del dato."""

    model_config = ConfigDict(extra="forbid")

    #: Hasta 99.999.999,9 — suficiente para cualquier odómetro real, y acotado
    #: para que un dedo torpe no meta un número absurdo sin que nadie lo note.
    reading: Decimal = Field(ge=0, le=Decimal("99999999.9"))


class OdometerExceptionCreate(BaseModel):
    """Pedir permiso para teclear sin foto.

    El motivo es una lista cerrada a propósito: un campo libre convertiría la
    excepción en un permiso permanente disfrazado que nadie podría revisar.
    `reason_note` aclara, no sustituye.
    """

    model_config = ConfigDict(extra="forbid")

    reason: OdometerExceptionReason
    reason_note: Optional[str] = Field(default=None, max_length=500)


class OdometerEvidenceRead(BaseModel):
    """El estado de un extremo, tal como lo lee el cliente.

    `ocr_detected_reading` viaja **junto a** `confirmed_reading`, nunca en su
    lugar: se puede ver qué sugirió la máquina y qué confirmó la persona, que
    son hechos distintos.

    La foto no se expone como URL: se pide por un endpoint autorizado que
    comprueba tenant y propiedad en cada lectura. `has_photo` sólo dice si la
    hay.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    work_session_id: int
    vehicle_id: Optional[int] = None
    evidence_type: str
    status: str
    evidence_method: Optional[str] = None
    confirmed_reading: Optional[Decimal] = None
    ocr_detected_reading: Optional[Decimal] = None
    captured_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[int] = None

    #: Qué dijo el análisis de malware. `not_configured` significa que este
    #: despliegue no tiene escáner, no que la foto esté limpia: son cosas
    #: distintas y el contrato no las confunde.
    scan_status: str = "not_configured"
    version: int


class OdometerExceptionRead(BaseModel):
    """Una solicitud de entrada manual, con su alcance a la vista."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    work_session_id: int
    vehicle_id: Optional[int] = None
    evidence_type: str
    status: str
    reason: str
    reason_note: Optional[str] = None
    requested_by: int
    requested_at: datetime
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
    consumed_at: Optional[datetime] = None
    version: int


class OdometerExceptionQueueRead(OdometerExceptionRead):
    """Una fila de la cola del administrador.

    Lleva el nombre de quien la pidió y la unidad del vehículo porque quien
    decide necesita saber sobre quién decide. Es un schema aparte del que recibe
    el supervisor: a él no se le devuelve su propio nombre, que ya conoce.
    """

    requested_by_name: str
    vehicle_unit: Optional[str] = None
    #: La zona de la jornada de la solicitud (T-1/T-2), para mostrar su hora
    #: en ella y no en la del administrador. Sólo lectura; las históricas
    #: traen únicamente el desfase.
    time_zone: Optional[str] = None
    utc_offset_minutes: Optional[int] = None


class OdometerPhotoResult(BaseModel):
    """Lo que se devuelve tras subir la foto.

    `ocr_suggestion` puede ser `null` y eso es normal: significa que no hay
    sugerencia, no que algo fallara. El supervisor teclea lo que ve y sigue
    siendo evidencia fotográfica, sin aprobación de nadie.
    """

    model_config = ConfigDict(extra="forbid")

    evidence: OdometerEvidenceRead
    ocr_suggestion: Optional[Decimal] = None


class OdometerSessionState(BaseModel):
    """Los dos extremos y la distancia derivada, si ya se puede afirmar."""

    model_config = ConfigDict(extra="forbid")

    start: Optional[OdometerEvidenceRead] = None
    end: Optional[OdometerEvidenceRead] = None
    #: `null` mientras falte alguna lectura. **No es cero**, y no es millaje de
    #: ruta: es evidencia de referencia de la jornada.
    odometer_distance: Optional[Decimal] = None


EVIDENCE_TYPES = tuple(t.value for t in OdometerEvidenceType)
