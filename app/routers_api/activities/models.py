"""
Ejecución de actividad tras la llegada (RTE05).

Qué cierra este dominio
------------------------
RTE04 dejó a propósito un cabo suelto: un viaje operativo que llega se queda en
`ARRIVED` porque lo que se hace al llegar no existía todavía. Esto es lo que
existía que faltaba, y con ello el viaje puede alcanzar `CLOSED` — pero **sólo**
después de que alguien haga el trabajo y diga cómo fue. Nunca porque se pidiera
terminar la jornada.

Un bloque, no un cronómetro por actividad
------------------------------------------
Es la decisión PD-01 y conviene entenderla antes de leer las tablas. Un
supervisor que llega a un cliente puede hacer tres cosas en la misma parada:
revisar el servicio, seguir una incidencia de asistencia y hablar de seguridad.
Eso es **una** parada con tres etiquetas, no tres paradas.

Así que hay un solo inicio, un solo fin, una sola duración, un solo resultado y
una sola nota. Las actividades seleccionadas son etiquetas de ese bloque, no
unidades de ejecución. Modelarlo al revés obligaría a inventar tres horas de
inicio que nadie midió.

Por qué se guarda la etiqueta y no sólo el identificador
---------------------------------------------------------
Las listas son del tenant y cambian: un administrador renombra "Safety
Follow-up", lo desactiva o lo retira. El identificador sigue resolviendo —las
filas sobreviven como lápida—, pero el **nombre** que tenía cuando se eligió, no.

Un histórico que se lee con el nombre de hoy cuenta una historia distinta de la
que ocurrió. Así que se guardan los dos: la referencia, para saber qué valor era;
y la etiqueta tal como estaba, para poder leer marzo como se veía en marzo.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin
from app.routers_api.trips.models import TripPurpose


class ActivityExecutionStatus(BusinessEnum):
    """Dos estados, y los dos finales son distinguibles para siempre.

    `COMPLETED` y `LEFT` no son lo mismo y no deben poder confundirse después:
    terminar el trabajo y marcharse antes de terminarlo son hechos operativos
    distintos, aunque los dos cierren el viaje y los dos exijan un resultado.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    LEFT = "left"


#: Los estados de los que ya no se sale. Se usan para el índice parcial que
#: impide dos ejecuciones vivas y para decidir si una transición es legal.
TERMINAL_EXECUTION_STATUSES = (
    ActivityExecutionStatus.COMPLETED.value,
    ActivityExecutionStatus.LEFT.value,
)


class TerminalAction(BusinessEnum):
    """Cómo terminó el bloque. `Leave` es una salida controlada, no un abandono."""

    COMPLETE = "complete"
    LEAVE = "leave"


#: Qué lista de actividades ofrece cada contexto **al llegar**, y cuántas exige.
#:
#: Sólo tres contextos seleccionan actividad, y es deliberado (matriz de
#: contextos de RTE05). Employee Visit y Office ya traen su dato desde antes de
#: salir —el motivo y el propósito—, y añadirles un selector post-llegada sería
#: duplicar lo que ya se preguntó para que todas las pantallas se parezcan.
#:
#: Un contexto que no está aquí **no acepta** actividades: enviarlas por API es
#: un error, no un extra que se ignora.
POSTARRIVAL_ACTIVITY_LIST: dict[str, str] = {
    TripPurpose.CLIENT_VISIT.value: "client_visit_activities",
    TripPurpose.RECRUITING.value: "recruiting_activities",
    TripPurpose.OTHER.value: "other_activities",
}

#: El dato que Check Delivery sólo puede conocer al llegar: quién recibió.
#:
#: No se mueve a la planificación —no se sabe antes de llegar quién firmará— ni
#: duplica el Delivery Type, que es del plan del viaje y ya está guardado allí.
RECEIVED_BY_LIST = "received_by"

#: El resultado de la parada. Lo mismo para todos los contextos.
#:
#: Es dato configurado del tenant, no un enum de la aplicación: CER lo decidió
#: así (PD-02) y por eso no hay `class Outcome(BusinessEnum)` en ninguna parte.
#: Las cuatro etiquetas sembradas son un punto de partida del tenant, no una
#: verdad del código.
OUTCOME_LIST = "outcomes"

#: Los contextos que **no** ejecutan bloque de actividad al llegar.
#:
#: Sólo HOME. Su viaje ya se cerró al llegar en RTE04 —volver a casa no es una
#: parada operativa— y esa decisión certificada no se toca.
NO_EXECUTION_PURPOSES = (TripPurpose.HOME.value,)


class ActivityExecution(TimeStampedModel, VersionedMixin):
    """El bloque de trabajo de una parada. **Uno por viaje.**

    Un solo bloque, garantizado por la base
    ----------------------------------------
    `uq_activity_execution_trip` es único sobre `trip_id`: reintentar el arranque
    o pulsarlo desde dos dispositivos no puede crear un segundo bloque. La
    comprobación en Python protege mientras nadie se olvide de llamarla; la
    restricción protege siempre.

    Tiempo de ocurrencia y tiempo de recepción
    -------------------------------------------
    Se mantiene la semántica certificada en RTE03 (D-10): `started_at` es cuándo
    lo pulsó la persona —que puede ser bastante antes si la acción esperó en la
    cola— y `started_received_at` cuándo lo supo el servidor. La duración sale de
    los dos instantes de ocurrencia, que es lo que de verdad duró la parada.
    """

    __tablename__ = "activity_execution"
    __table_args__ = (
        # Un bloque por viaje. No es "uno vivo": es uno, punto. Una parada se
        # ejecuta una vez, y reabrirla sería inventar una segunda visita.
        UniqueConstraint("trip_id", name="uq_activity_execution_trip"),
        # El par que hace posible referenciar esta fila **con su compañía** desde
        # las actividades seleccionadas. Es la misma convención que ya usan
        # `trip`, `work_session` y `standard_value`: sin este único, PostgreSQL
        # no acepta la clave foránea compuesta que hace imposible cruzar tenants.
        UniqueConstraint("id", "company_id", name="uq_activity_execution_id_company"),
        # El viaje pertenece a esta compañía. Con la clave compuesta, referenciar
        # el viaje de otro tenant es imposible por construcción, no por cuidado.
        ForeignKeyConstraint(
            ["trip_id", "company_id"],
            ["trip.id", "trip.company_id"],
            name="fk_activity_execution_trip_same_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_activity_execution_session_same_company",
            ondelete="RESTRICT",
        ),
        # Terminar exige las dos cosas: la hora y el resultado. Un bloque
        # terminal sin resultado sería exactamente el hecho fabricado que las
        # instrucciones prohíben.
        CheckConstraint(
            "(status = 'in_progress' AND ended_at IS NULL AND terminal_action IS NULL"
            " AND outcome_standard_value_id IS NULL)"
            " OR (status IN ('completed', 'left') AND ended_at IS NOT NULL"
            " AND terminal_action IS NOT NULL"
            " AND outcome_standard_value_id IS NOT NULL)",
            name="ck_activity_execution_terminal_facts",
        ),
        # Y no puede haber terminado antes de empezar.
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_activity_execution_ends_after_start",
        ),
        Index("ix_activity_execution_session", "company_id", "work_session_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_session_id = Column(Integer, nullable=False, index=True)
    #: Sin `index=True`: `uq_activity_execution_trip` ya es un índice sobre esta
    #: columna. Un segundo índice idéntico sólo cuesta escrituras.
    trip_id = Column(Integer, nullable=False)
    #: Quién ejecutó. Sale de la sesión autenticada, nunca del cuerpo.
    user_id = Column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        server_default=ActivityExecutionStatus.IN_PROGRESS.value,
    )
    terminal_action = Column(String(10), nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=False)
    started_received_at = Column(DateTime(timezone=True), nullable=False)
    started_at_source = Column(String(20), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    ended_received_at = Column(DateTime(timezone=True), nullable=True)
    ended_at_source = Column(String(20), nullable=True)

    #: El resultado: referencia al valor configurado **y** su etiqueta de
    #: entonces. Ver la explicación del módulo: el identificador dice cuál era,
    #: la etiqueta permite leer el histórico como se veía.
    outcome_standard_value_id = Column(Integer, nullable=True)
    outcome_label = Column(String(120), nullable=True)

    #: Quién recibió la entrega. Sólo Check Delivery, y sólo al llegar.
    received_by_standard_value_id = Column(Integer, nullable=True)
    received_by_label = Column(String(120), nullable=True)

    #: Opcional siempre. No se vuelve obligatoria para compensar la falta de un
    #: dato estructurado: si algo hay que registrar en firme, se modela.
    notes = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ActivityExecution trip={self.trip_id} status={self.status} "
            f"action={self.terminal_action}>"
        )


class ActivityExecutionActivity(TimeStampedModel):
    """Una actividad seleccionada para ese bloque. De una a varias.

    No lleva estado propio ni horas propias: es una **etiqueta** del bloque. Todo
    lo que ocurre —cuándo empezó, cuánto duró, cómo acabó— pertenece a la
    ejecución, no a cada actividad por separado (PD-01).
    """

    __tablename__ = "activity_execution_activity"
    __table_args__ = (
        # La misma actividad no se selecciona dos veces en la misma parada.
        UniqueConstraint(
            "activity_execution_id",
            "standard_value_id",
            name="uq_activity_execution_value",
        ),
        ForeignKeyConstraint(
            ["activity_execution_id", "company_id"],
            ["activity_execution.id", "activity_execution.company_id"],
            name="fk_activity_value_execution_same_company",
            ondelete="CASCADE",
        ),
        # `RESTRICT` y no `CASCADE`: el valor configurado puede desactivarse o
        # retirarse como lápida, pero no desaparecer de debajo de un histórico.
        ForeignKeyConstraint(
            ["standard_value_id", "company_id"],
            ["standard_value.id", "standard_value.company_id"],
            name="fk_activity_value_standard_same_company",
            ondelete="RESTRICT",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Tampoco lleva índice propio: `uq_activity_execution_value` empieza por
    #: esta columna, así que las lecturas por bloque ya lo aprovechan.
    activity_execution_id = Column(Integer, nullable=False)
    standard_value_id = Column(Integer, nullable=False)

    #: La etiqueta tal como estaba al seleccionarla. Ver el módulo.
    label = Column(String(120), nullable=False)
    #: El orden en que se eligieron, para poder enseñarlas como se eligieron.
    sort_order = Column(Integer, nullable=False, server_default="0")

    def __repr__(self) -> str:
        return f"<ActivityExecutionActivity {self.label!r}>"
