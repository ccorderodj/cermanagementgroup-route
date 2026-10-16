"""
Contratos de Reports (RTE09).

Coste estimado: el número y lo que significa, por separado
----------------------------------------------------------
`estimated_fuel_cost` es **siempre un número**: el valor visible. Cuando no hay
precio en la base es `0`, por decisión de producto (autorización §8). Lo que
dice si ese número es un resultado o una espera es `fuel_cost_status`, que
viaja **al lado** en cada nivel —resumen, grupo, fila del desglose—:

* `calculated` — todas las jornadas que aportan se calcularon con una referencia
  real. Un `0` aquí es un cero de verdad (jornadas sin millas).
* `partial` — unas sí y otras todavía no: el número suma sólo las calculadas.
* `waiting_reference` — ninguna calculada; lo que falta es el precio en la base.
* `missing_input` — ninguna calculada; falta una entrada de la jornada (estado,
  grado o MPG). `fuel` dice cuántas y cuál.
* `none` — no hay jornadas con viajes en ese corte.

Así el cliente nunca deduce el significado de un `0` formateado (RTE09 §12).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

ReportRange = Literal["week", "month", "year"]
ReportGroupedBy = Literal["day", "week", "month"]
FuelCostStatus = Literal[
    "calculated", "partial", "waiting_reference", "missing_input", "none"
]


class ReportSupervisor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    name: str


class ReportMetrics(BaseModel):
    """Lo que se mide igual en el resumen, en cada grupo y en cada fila."""

    model_config = ConfigDict(extra="forbid")

    #: Millas oficiales de los viajes **calculados**. Nunca odómetro ni línea
    #: recta; los pendientes y los sin cifra no suman y se dicen aparte.
    official_miles: Decimal
    mileage_pending: bool
    #: Viajes que terminaron **sin** kilometraje. No es lo mismo que pendiente.
    mileage_unresolved: int = 0
    #: Tiempo de actividad: suma de bloques **terminados**, la definición del
    #: explorador. Un bloque abierto no tiene duración todavía.
    activity_seconds: int
    has_open_activity: bool
    #: Bloques de actividad. Uno por parada, por muchas actividades que se
    #: seleccionaran en ella.
    activities: int
    #: Galones estimados de las jornadas con MPG; `None` si ninguna lo tiene.
    estimated_gallons: Optional[Decimal] = None
    estimated_fuel_cost: Decimal
    fuel_cost_status: FuelCostStatus


class ReportGroup(ReportMetrics):
    """Una fila de *By day / By week / By month*: sólo las que tienen datos."""

    start: date
    end: date


class ReportPeriod(BaseModel):
    """Un periodo o subgrupo, por sus fechas. Es el identificador estable: la
    pantalla nunca devuelve una etiqueta como `Mon Oct 12`."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


class ReportBreakdownRow(ReportMetrics):
    """Una fila del *Activity Breakdown*: un **propósito de viaje** (V0.7)."""

    purpose: str


class ReportActivityType(BaseModel):
    """Cuántas veces se seleccionó una actividad. Sólo ocurrencias: una parada
    con tres actividades suma una a cada una y **no** reparte millas ni tiempo."""

    model_config = ConfigDict(extra="forbid")

    label: str
    count: int


class ReportFuel(BaseModel):
    """Cómo están las estimaciones de las jornadas del corte, contadas."""

    model_config = ConfigDict(extra="forbid")

    sessions: int
    calculated: int
    #: Calculadas y ya congeladas: no cambiarán.
    final: int
    waiting_reference: int
    missing_input: int
    #: Por entrada que falta: `operational_state`, `fuel_grade`, `operational_mpg`.
    missing: dict[str, int]


class ReportView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: ReportRange
    #: El periodo **en curso**, resuelto por el servidor. La pantalla formatea.
    start: date
    end: date
    grouped_by: ReportGroupedBy
    supervisors: list[ReportSupervisor]
    #: `None` es *All Supervisors*, el valor por defecto del V0.7.
    supervisor_user_id: Optional[int] = None

    #: Las opciones del selector de periodo concreto, de la más reciente a la
    #: más antigua: desde el periodo en curso del servidor hacia atrás, hasta
    #: el primer dato del alcance autorizado y con un tope por rango
    #: (`service.OPCIONES_MAXIMAS`). Siempre incluye el periodo mostrado.
    periods: list[ReportPeriod]

    #: KPIs y grupos son siempre del periodo principal. Sólo el desglose
    #: (`breakdown`, `breakdown_excluded`, `activity_types`) se acota al
    #: subgrupo elegido, si lo hay.
    summary: ReportMetrics
    groups: list[ReportGroup]
    #: El subgrupo al que se acota el desglose; `None` es el periodo entero.
    selected_group: Optional[ReportPeriod] = None
    breakdown: list[ReportBreakdownRow]
    #: Lo que no tiene fila en el desglose del V0.7: los regresos a casa, que
    #: suman millas pero no son una visita. Viaja para que el total se pueda
    #: explicar: `Σ breakdown + Σ excluded = summary`.
    breakdown_excluded: list[ReportBreakdownRow]
    activity_types: list[ReportActivityType]
    fuel: ReportFuel
