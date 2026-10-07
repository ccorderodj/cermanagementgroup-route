"""
Contratos de Today / Live.

Qué es esta superficie
----------------------
Un **modelo de lectura** sobre hechos que ya existen: Work Session, Trip,
Activity y el millaje oficial. No añade persistencia ni estado propio, y no
puede: duplicar el "estado actual" en una tabla para el panel significaría tener
dos versiones del mismo hecho, y acabarían diciendo cosas distintas.

De dónde salen los estados visibles
------------------------------------
El mockup aprobado V0.7 enseña cuatro, y son los que esta API devuelve. No se
inventa ninguno y no se expone un enum interno nuevo: la traducción de
`WorkSession` + `Trip` + `Activity` a la etiqueta visible la hace el **servidor**,
porque es una regla de dominio y no una decisión de pantalla.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


#: Los cuatro estados que enseña V0.7, con sus etiquetas aprobadas.
#:
#: `statusMeta()` del mockup:
#:     route    -> "On Route"
#:     activity -> "In Activity"
#:     ended    -> "Work Ended"
#:     (resto)  -> "Working"
#:
#: Se devuelve el código, no la etiqueta: la cadena visible pertenece a la capa
#: de presentación y traducirla aquí ataría el contrato al idioma de la interfaz.
LiveStatus = Literal["route", "activity", "ended", "working", "not_started"]


class LiveSupervisor(BaseModel):
    """Una fila de la lista de supervisores, que es la superficie principal.

    `not_started` no está en el mockup y no es un estado nuevo: V0.7 dibuja a
    todos los supervisores autorizados, y alguien que hoy no ha empezado no
    puede desaparecer de la lista ni aparecer como "Working". FR-09 lo exige de
    forma explícita —*no ocultes a un supervisor porque no tenga jornada*— así
    que se distingue aquí y la pantalla lo presenta con la etiqueta neutra de la
    línea base.
    """

    model_config = ConfigDict(extra="forbid")

    supervisor_profile_id: int
    user_id: int
    name: str
    initials: str

    status: LiveStatus
    #: Desde cuándo dura el estado actual. `None` si no ha empezado la jornada.
    since: Optional[datetime] = None

    #: El vehículo de la **instantánea de la jornada**, no el asignado hoy: si
    #: el administrador reasigna después, esta fila sigue hablando del vehículo
    #: con el que se condujo.
    vehicle_label: Optional[str] = None

    #: Contexto operativo actual, de los hechos del viaje. `activity_label` es
    #: el propósito vigente y `activity_reference` su referencia.
    activity_label: Optional[str] = None
    activity_reference: Optional[str] = None

    #: Millas **oficiales** del día. Nunca el delta de odómetro ni una
    #: distancia en línea recta.
    official_miles: Decimal
    #: Si queda algún viaje del día cuyo millaje oficial todavía no está
    #: calculado. La pantalla lo dice en vez de presentar el total como final.
    mileage_pending: bool
    #: Cuántos viajes del día terminaron **sin** kilometraje: faltó evidencia de
    #: ubicación, o el routing agotó su reintento acotado.
    #:
    #: No es lo mismo que `mileage_pending`. Aquello es «todavía no»; esto es
    #: «ya no va a haber cifra». Sin este dato las dos situaciones, y también
    #: «no hubo ningún viaje», se dibujaban como el mismo `0.0 mi` mudo.
    mileage_unresolved: int = 0

    activities_today: int

    #: Rendimiento y combustible del vehículo. Viajan porque V0.7 los usa en el
    #: detalle; el **precio** por galón no existe en el dominio, así que el
    #: coste estimado no se calcula aquí ni en ninguna parte (ver el reporte).
    operational_mpg: Optional[Decimal] = None
    fuel_grade: Optional[str] = None


class LiveSummary(BaseModel):
    """Las cuatro tarjetas del encabezado, en el orden de V0.7."""

    model_config = ConfigDict(extra="forbid")

    supervisors_working: int
    supervisors_total: int
    total_miles: Decimal
    on_route: int
    in_activity: int


class LiveToday(BaseModel):
    """La respuesta completa de la página, en una sola lectura.

    Una sola llamada y no varias a propósito: la pantalla se refresca sola cada
    pocos segundos, y reconstruir el estado desde cinco endpoints multiplicaría
    ese tráfico y obligaría al navegador a recomponer reglas de dominio que son
    del servidor.
    """

    model_config = ConfigDict(extra="forbid")

    #: El día de negocio que se está mostrando, con la semántica de
    #: `session_date` — no la fecha UTC de los eventos.
    session_date: date
    #: Cuándo se leyó. La pantalla lo usa para decir desde cuándo es lo que ve.
    generated_at: datetime
    summary: LiveSummary
    supervisors: list[LiveSupervisor]
