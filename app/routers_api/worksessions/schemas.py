"""Contratos de la Jornada."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkSessionStart(BaseModel):
    """Lo único que el cliente puede aportar: evidencia de tiempo local.

    Todo lo demás —quién, en qué compañía, con qué vehículo, con qué reloj
    autoritativo— lo decide el servidor. No hay un campo `user_id` ni
    `company_id` aquí a propósito: aceptarlos del cuerpo sería la puerta que
    las reglas del repositorio prohíben (AGENTS.md — el tenant y el actor
    nunca llegan del cliente).
    """

    model_config = ConfigDict(extra="forbid")

    #: La hora local que el dispositivo dice tener en este instante. Evidencia,
    #: no autoridad: el servidor usa su propio reloj para `started_at`.
    device_captured_at: Optional[datetime] = None
    #: Minutos al este de UTC (p. ej. -240 para EDT). De aquí sale
    #: `session_date`, no del reloj del dispositivo — ver D-10 en el informe.
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class WorkSessionEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_captured_at: Optional[datetime] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class WorkSessionVehicleSnapshot(BaseModel):
    """Lo que se congeló del vehículo al empezar. Puede no haber ninguno."""

    model_config = ConfigDict(from_attributes=True)

    vehicle_id: int
    mpg_snapshot: Optional[Decimal] = None
    #: Resueltos por join en el momento de leer, para que la pantalla no tenga
    #: que hacer una segunda llamada. No son parte del snapshot histórico: si
    #: el vehículo cambia de nombre, esto refleja el nombre actual.
    unit: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None


class WorkSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    session_date: date
    started_at: datetime
    ended_at: Optional[datetime] = None
    vehicle_id: Optional[int] = None
    mpg_snapshot: Optional[Decimal] = None
    version: int
    created_at: datetime
    updated_at: datetime


class CurrentWorkSessionResponse(BaseModel):
    """El estado autoritativo de `GET /worksessions/current`.

    Diseñado para crecer: RTE04 añadirá una clave `current_trip` y RTE05
    `current_activity` a este mismo cuerpo, nunca un segundo endpoint de
    "estado actual" compitiendo con este. En RTE03 solo existe la jornada, así
    que solo se declara esa clave — añadir claves `null` para dominios que
    todavía no existen sería simular algo que no está construido.
    """

    model_config = ConfigDict(extra="forbid")

    work_session: Optional[WorkSessionRead] = None
