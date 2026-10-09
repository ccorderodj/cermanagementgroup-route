"""Contratos de entrada y salida de vehículos, perfiles y asignaciones."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core import schema
from app.routers_api.vehicles.models import FuelGrade


# ── Vehículo ────────────────────────────────────────────────────────────────


class VehicleBase(BaseModel):
    make: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    year: int = Field(ge=1900, le=2100)
    unit: str = Field(min_length=1, max_length=40)
    fuel_grade: FuelGrade
    operational_mpg: Decimal = Field(gt=0, le=Decimal("999.99"))

    @field_validator("make", "model", "unit")
    @classmethod
    def _sin_espacios_sobrantes(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("must not be blank")
        return limpio


class VehicleCreate(VehicleBase):
    model_config = ConfigDict(extra="forbid")


class VehicleUpdate(BaseModel):
    """Edición parcial. `version` viaja para el control de concurrencia."""

    model_config = ConfigDict(extra="forbid")

    make: Optional[str] = Field(default=None, min_length=1, max_length=60)
    model: Optional[str] = Field(default=None, min_length=1, max_length=60)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=40)
    fuel_grade: Optional[FuelGrade] = None
    operational_mpg: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("999.99"))
    is_active: Optional[bool] = None
    #: La versión que el cliente leyó. Sin ella no participa en el control de
    #: concurrencia y la última escritura gana (ver `ensure_version`).
    version: Optional[int] = None


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    make: str
    model: str
    year: int
    unit: str
    fuel_grade: str
    operational_mpg: Decimal
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class VehiclesPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        search: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        fuel_grade: Optional[FuelGrade] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.search = (search or "").strip() or None
        self.is_active = is_active
        self.fuel_grade = fuel_grade.value if fuel_grade else None


# ── Perfil de supervisor ────────────────────────────────────────────────────


class SupervisorProfileCreate(BaseModel):
    """Designa como supervisor de Route a un usuario que ya existe.

    Sólo viaja el `user_id`: nombre y correo son de `user` y no se copian aquí.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: int


class SupervisorProfileRead(BaseModel):
    """El perfil con la identidad resuelta desde `user`, no duplicada en él."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    #: Vehículo vigente, derivado de `vehicle_assignment`. `None` es un estado
    #: normal: un supervisor recién designado todavía no conduce nada.
    current_vehicle: Optional[VehicleRead] = None
    #: Override de zona horaria (T-1/T-2). `None`: automática, del dispositivo.
    operational_time_zone: Optional[str] = None


class SupervisorProfileUpdate(BaseModel):
    """Ciclo de vida de la designación.

    Retirar a alguien de supervisor **desactiva** el perfil; no lo borra. Sus
    asignaciones pasadas y —cuando existan— sus jornadas siguen apuntando a él,
    y borrarlo dejaría esa historia hablando de alguien que no existe.
    """

    model_config = ConfigDict(extra="forbid")

    is_active: bool
    version: Optional[int] = None


class SupervisorTimeZoneUpdate(BaseModel):
    """El override de zona horaria del supervisor (T-1/T-2, D1).

    **Opcional y para excepciones.** `None` lo quita y la zona vuelve a salir
    del dispositivo en cada jornada, que es el comportamiento por defecto. Un
    identificador que `zoneinfo` no reconoce se rechaza con 422: una zona mal
    escrita aplicada en silencio fecharía mal todas sus jornadas.
    """

    model_config = ConfigDict(extra="forbid")

    operational_time_zone: Optional[str] = Field(default=None, max_length=64)
    version: Optional[int] = None


class SupervisorCandidateRead(BaseModel):
    """Un usuario del tenant y su relación con CER Route.

    Hace visible la cadena completa en una sola fila: quién es (identidad del
    núcleo), si está designado supervisor, y qué vehículo conduce. Los tres son
    conceptos distintos y se leen como tales; no se funden en una entidad.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    username: str
    membership_active: bool
    role_name: Optional[str] = None

    #: `None` = este usuario todavía no es supervisor de Route.
    supervisor_profile_id: Optional[int] = None
    supervisor_active: Optional[bool] = None
    supervisor_version: Optional[int] = None
    #: Override de zona horaria (T-1/T-2). `None`: automática, del dispositivo.
    supervisor_time_zone: Optional[str] = None
    current_vehicle: Optional[VehicleRead] = None


# ── Asignación de vehículo ──────────────────────────────────────────────────


class VehicleAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: int
    #: Si no se envía, la asignación empieza ahora, con el reloj del servidor.
    effective_from: Optional[datetime] = None


class VehicleAssignmentEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Si no se envía, se cierra ahora, con el reloj del servidor.
    effective_to: Optional[datetime] = None


class VehicleAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supervisor_profile_id: int
    vehicle_id: int
    effective_from: datetime
    #: `None` = vigente.
    effective_to: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Datos del vehículo resueltos por join para que la pantalla de historial
    # no necesite una segunda llamada por fila.
    vehicle_unit: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_year: Optional[int] = None
