"""Contratos de la Jornada."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.routers_api.trips.schemas import TripRead


class WorkSessionStart(BaseModel):
    """Lo único que el cliente puede aportar: evidencia de tiempo local.

    Todo lo demás —quién, en qué compañía, con qué vehículo, con qué reloj
    autoritativo— lo decide el servidor. No hay un campo `user_id` ni
    `company_id` aquí a propósito: aceptarlos del cuerpo sería la puerta que
    las reglas del repositorio prohíben (AGENTS.md — el tenant y el actor
    nunca llegan del cliente).
    """

    model_config = ConfigDict(extra="forbid")

    #: Cuándo pulsó el botón el supervisor, según el dispositivo. Se captura al
    #: **encolar** la acción, no al enviarla: para una acción que esperó sin
    #: cobertura es la única fuente que conoce el instante real. El servidor la
    #: valida contra lo que sabe con certeza antes de aceptarla y guarda
    #: siempre, por separado, su propia hora de recepción.
    device_captured_at: Optional[datetime] = None
    #: Minutos al este de UTC (p. ej. -240 para EDT). Decide a qué fecha del
    #: calendario local pertenece la ocurrencia — ver D-10 en el informe.
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)


class WorkSessionEnd(BaseModel):
    """Cerrar la jornada. Con un viaje en curso, es una revisión.

    `end_anyway` es la confirmación **explícita** del supervisor tras ver que
    todavía está en ruta. Sin ella, el servidor rechaza el cierre y devuelve el
    viaje vivo para que la pantalla pueda ofrecer "Continue Working" o "End
    Work Anyway" (D-07). No se cierra por descuido lo que alguien dejó a medias.
    """

    model_config = ConfigDict(extra="forbid")

    device_captured_at: Optional[datetime] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-720, le=840)
    end_anyway: bool = False


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
    """La jornada tal como la lee el cliente.

    `started_at`/`ended_at` son **ocurrencia** —cuándo pulsó el botón el
    supervisor—, que es lo que la pantalla debe mostrar y lo que RTE04 usará
    para ordenar Trips. `*_received_at` y `*_at_source` acompañan al dato para
    que el consumidor pueda ver si esa hora es evidencia del dispositivo o una
    aproximación por hora de recepción, en vez de tener que asumir una de las
    dos cosas.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    session_date: date
    started_at: datetime
    started_received_at: datetime
    started_at_source: str
    ended_at: Optional[datetime] = None
    ended_received_at: Optional[datetime] = None
    ended_at_source: Optional[str] = None
    vehicle_id: Optional[int] = None
    mpg_snapshot: Optional[Decimal] = None
    version: int
    created_at: datetime
    updated_at: datetime


class CurrentWorkSessionResponse(BaseModel):
    """El estado autoritativo de `GET /worksessions/current`.

    El sobre crece, no se duplica. RTE03 traía sólo la jornada; RTE04 añade
    `current_trip` aquí mismo, y RTE05 añadirá `current_activity` de la misma
    forma. Nunca un segundo endpoint de "estado actual" compitiendo con este:
    dos fuentes de verdad para la misma pregunta acaban respondiendo cosas
    distintas.

    `current_trip` es el viaje **no terminal** de la jornada, si lo hay. Un
    viaje operativo en `ARRIVED` sigue siendo el actual —espera a RTE05—,
    mientras que uno `CLOSED` o `INTERRUPTED` ya no lo es. Sin viaje vivo la
    clave vale `null`, no un marcador de posición: fabricar uno sería fingir un
    estado que no existe.
    """

    model_config = ConfigDict(extra="forbid")

    work_session: Optional[WorkSessionRead] = None
    current_trip: Optional[TripRead] = None
