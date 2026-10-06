"""
Contratos del Activity Explorer.

Qué es esta superficie
----------------------
Un **modelo de lectura** sobre hechos ya certificados: Work Session, Trip y
Activity Execution. No añade persistencia y no puede: duplicar la historia en
una tabla propia del explorador sería tener dos versiones del mismo hecho, y
acabarían diciendo cosas distintas (§11).

Por qué el servidor devuelve fechas y no textos
------------------------------------------------
La **convención** de los periodos es dominio: la semana empieza en lunes y se
recorta al mes, y el día es el día de negocio de la jornada. Eso lo decide el
servidor y se puede probar. El **formato** visible —`Sep 14–20`, `Mon Sep 14`,
`January`— es presentación, y se queda en la pantalla, igual que las etiquetas
de estado de Today / Live. Así la pantalla no reconstruye ninguna regla y el
servidor no se ata al idioma de la interfaz.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

#: Los cuatro rangos de las pestañas de V0.7, en su orden.
ExplorerRange = Literal["day", "week", "month", "year"]

#: El nivel por el que agrupa cada rango, según `groupRows()` de V0.7:
#: año → meses, mes → semanas, semana → días. El día no agrupa: enseña paradas.
ExplorerGroupedBy = Literal["month", "week", "day"]


class ExplorerGroup(BaseModel):
    """Una fila de grupo: un mes, una semana o un día con registros.

    V0.7 sólo dibuja los grupos que existen —sus días van de lunes a viernes
    porque el fin de semana no tuvo jornada— así que un periodo sin registros
    no aparece. No se fabrican grupos vacíos (FR-02).
    """

    model_config = ConfigDict(extra="forbid")

    #: El primer y el último día de negocio del grupo. La pantalla formatea; la
    #: convención es de aquí.
    start: date
    end: date

    #: La fecha con la que se baja un nivel. Es el primer día del grupo, que es
    #: lo que el botón `View month/week/day` necesita para anclar la vista
    #: siguiente.
    drill_date: date

    #: Millas **oficiales** del periodo. Nunca delta de odómetro ni distancia
    #: en línea recta.
    official_miles: Decimal
    #: Si algún viaje del periodo todavía no tiene millaje calculado. La
    #: pantalla lo dice en vez de presentar el total como final.
    mileage_pending: bool

    activities: int
    #: Tiempo de actividad del periodo, en segundos. Suma de las duraciones de
    #: los bloques **terminados**; un bloque en curso no tiene duración todavía
    #: y por eso no suma.
    activity_seconds: int
    #: Y si quedó algún bloque sin terminar, para que la pantalla pueda decir
    #: `In progress` como en la línea base en vez de redondear a la baja.
    has_open_activity: bool


class ExplorerActivity(BaseModel):
    """Una parada: el bloque de ejecución de un viaje, con su contexto.

    Es **un** hecho histórico, no varios. Si en la parada se seleccionaron tres
    actividades, las tres se enseñan y comparten horas, resultado y nota: el
    modelo certificado tiene un bloque por viaje y PR-03 prohíbe fabricar
    historias de ejecución separadas por cada etiqueta.
    """

    model_config = ConfigDict(extra="forbid")

    activity_execution_id: int
    trip_id: int

    #: El propósito del viaje: la razón del desplazamiento. No es la actividad
    #: (PR-04); va en el encabezado de la tarjeta, como en V0.7.
    purpose: str
    #: La referencia de contexto del viaje: cliente, empleado, oficina, área.
    context_reference: Optional[str] = None

    #: Lo que cualificó la parada. Para los contextos con lista post-llegada
    #: —Client Visit, Recruiting, Other— son las actividades seleccionadas, con
    #: la etiqueta **congelada** al seleccionarlas. Para los que no la tienen
    #: —Employee Visit, Office, Check Delivery— el dominio lo registra antes de
    #: salir, y entonces viaja en `purpose_detail`.
    activity_labels: list[str]
    purpose_detail: Optional[str] = None

    #: Las horas de ocurrencia. `trip_started_at` es la salida y `ended_at` el
    #: cierre del bloque: entre las dos está el tramo que V0.7 llama
    #: `activity span`.
    trip_started_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

    #: Millas oficiales del viaje de esta parada.
    official_miles: Decimal
    mileage_pending: bool

    #: Cómo acabó. `terminal_action` es la acción y `outcome_label` el resultado
    #: configurado, con su etiqueta de entonces.
    terminal_action: Optional[str] = None
    outcome_label: Optional[str] = None
    notes: Optional[str] = None

    #: Quién la ejecutó. Viaja porque el explorador es de administración y el
    #: selector de V0.7 elige supervisor.
    supervisor_user_id: int
    supervisor_name: str


class ExplorerSummary(BaseModel):
    """Las cuatro mini-estadísticas del día, en el orden de V0.7."""

    model_config = ConfigDict(extra="forbid")

    official_miles: Decimal
    mileage_pending: bool
    activity_seconds: int
    has_open_activity: bool
    activities: int


class ExplorerSupervisor(BaseModel):
    """Una opción del selector de supervisor. Autorizada en el servidor."""

    model_config = ConfigDict(extra="forbid")

    user_id: int
    name: str


class ExplorerView(BaseModel):
    """Un nivel del explorador, y sólo uno.

    Pedir un nivel por petición es lo que mantiene la lectura acotada (§15):
    abrir la página no trae la historia entera del tenant, y bajar por una rama
    no trae las demás. La paginación técnica no se asoma al producto porque no
    hace falta: un periodo tiene los grupos que tiene.
    """

    model_config = ConfigDict(extra="forbid")

    range: ExplorerRange
    #: El periodo que se está mirando, ya resuelto por el servidor.
    start: date
    end: date
    #: Por qué nivel agrupa esta vista. `None` en el día, que no agrupa.
    grouped_by: Optional[ExplorerGroupedBy] = None

    #: Los supervisores que este administrador puede explorar.
    supervisors: list[ExplorerSupervisor]
    #: Cuál se está mirando. `None` si la compañía no tiene supervisores.
    supervisor_user_id: Optional[int] = None

    groups: list[ExplorerGroup]
    #: Sólo en el día: el resumen y las paradas.
    summary: Optional[ExplorerSummary] = None
    activities: list[ExplorerActivity]
