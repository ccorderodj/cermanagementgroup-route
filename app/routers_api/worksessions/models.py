"""
Jornada del supervisor (Work Session) — RTE03.

`none → ACTIVE → ENDED`, sin Trip ni Activity: esos dominios no existen
todavía (RTE04/RTE05), y una Jornada con cero Trips es un resultado válido, no
uno incompleto (A-1, certificado en RTE01).

La identidad de quien trabaja es `user_id`, la del núcleo — **no**
`supervisor_profile_id`. Son dos preguntas distintas: quién puede ejecutar
acciones de Jornada lo decide la capacidad `route.worksession.execute` del rol
(RBAC), y quién tiene un perfil de campo con vehículo asignado lo decide
`supervisor_profile` (RTE02). Un usuario con la capacidad pero sin perfil de
supervisor tiene una Jornada perfectamente válida, sin vehículo — es
exactamente el caso que `mpg_snapshot` nulo cubre (§6.1 de las instrucciones).
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin


class WorkSessionStatus(BusinessEnum):
    ACTIVE = "active"
    ENDED = "ended"


class WorkSessionTimeSource(BusinessEnum):
    """De dónde salió la hora de ocurrencia que se guardó.

    `DEVICE`: se aceptó la evidencia del dispositivo — el supervisor pulsó el
    botón en ese instante, aunque el servidor lo haya recibido más tarde.

    `SERVER_RECEIPT`: no había evidencia utilizable (cliente que no la envía) o
    la que había era contradictoria (ver `_resolve_occurrence` en el servicio),
    así que la hora de recepción se usa como aproximación. No es lo mismo que
    saber cuándo ocurrió, y por eso se distingue en una columna en vez de
    quedar indistinguible del caso anterior.
    """

    DEVICE = "device"
    SERVER_RECEIPT = "server_receipt"


class WorkSession(TimeStampedModel, VersionedMixin):
    """Una jornada, del `Start Work` al `End Work`.

    Una sola vigente por supervisor, garantizado por la base
    (`uq_work_session_one_active`, índice único **parcial**): dos peticiones
    simultáneas de `Start Work` no pueden producir dos filas `ACTIVE`. La
    segunda choca contra el índice; el servicio la recupera y devuelve la
    misma jornada que ya existía, en vez de fallar visiblemente para el
    supervisor que solo pulsó el botón dos veces (§4 de las instrucciones).

    `session_date` se calcula **una vez**, al crear la fila, y nunca se
    recalcula — ni en `End Work` ni por ningún otro camino. Es la fecha del
    calendario local en el momento de `Start Work` (D-10), y una jornada que
    cruza medianoche se queda con la fecha en la que empezó.

    **Dos relojes, dos hechos distintos.** `started_at`/`ended_at` dicen cuándo
    *ocurrió* la acción; `started_received_at`/`ended_received_at`, cuándo la
    *recibió* el servidor. Para una acción online son el mismo instante; para
    una encolada sin cobertura no lo son, y guardar solo el segundo haría que
    el retraso de sincronización se leyera como la jornada real — un `Start
    Work` del viernes por la noche sincronizado el sábado aparecería como
    sábado. `session_date` sale de la ocurrencia, no de la recepción.
    `*_at_source` dice de qué reloj salió cada ocurrencia, porque una evidencia
    ausente o contradictoria tiene que poder distinguirse de una aceptada.

    El snapshot de vehículo (`vehicle_id`, `mpg_snapshot`) es histórico: se
    copia una vez al crear la fila y no se vuelve a tocar. Si el administrador
    reasigna el vehículo o cambia el MPG operativo del vehículo maestro
    después, esta fila sigue diciendo lo que era cierto cuando empezó la
    jornada (RTE01 D-02.8, aplicado aquí a la jornada en vez de al millaje).
    """

    __tablename__ = "work_session"
    __table_args__ = (
        WorkSessionStatus.check("status", name="ck_work_session_status"),
        WorkSessionTimeSource.check(
            "started_at_source", name="ck_work_session_started_at_source"
        ),
        WorkSessionTimeSource.check(
            "ended_at_source", name="ck_work_session_ended_at_source"
        ),
        # Una jornada no puede terminar antes de empezar. Lo garantiza la base
        # y no solo el servicio: la evidencia de tiempo llega de un reloj que
        # no controlamos, así que la comprobación tiene que sobrevivir a
        # cualquier camino —incluida una migración de datos o un `UPDATE`
        # manual— que intente escribir una duración negativa (invariante 6).
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_work_session_end_after_start",
        ),
        UniqueConstraint("id", "company_id", name="uq_work_session_id_company"),
        ForeignKeyConstraint(
            ["vehicle_id", "company_id"],
            ["vehicle.id", "vehicle.company_id"],
            name="fk_work_session_vehicle_same_company",
            ondelete="RESTRICT",
        ),
        # Una jornada vigente por supervisor. Parcial a propósito: las
        # cerradas pueden repetirse cuantas veces haga falta — es exactamente
        # el mismo patrón que `uq_vehicle_assignment_current` en RTE02.
        Index(
            "uq_work_session_one_active",
            "company_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_work_session_company_user_date", "company_id", "user_id", "session_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: El núcleo, no el perfil de Route. Nunca llega del cliente: siempre es
    #: `current_user.id` de la sesión autenticada (§9 de las instrucciones).
    user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        String(20), nullable=False, server_default=WorkSessionStatus.ACTIVE.value
    )

    #: Fecha del calendario **local** en `Start Work` (D-10). Inmutable tras la
    #: creación — ningún código de este módulo la vuelve a escribir.
    session_date = Column(Date, nullable=False)

    #: **Cuándo ocurrió** el `Start Work`: el instante en el que el supervisor
    #: pulsó el botón, no el instante en el que el servidor se enteró. Para una
    #: acción online las dos cosas coinciden; para una encolada sin cobertura
    #: pueden separarse horas, y representar la sincronización como si fuera la
    #: jornada es precisamente el error que corrige el cierre 002.
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    ended_at = Column(DateTime(timezone=True), nullable=True)

    #: **Cuándo lo recibió el servidor.** Reloj propio, siempre, sin excepción y
    #: sin que ninguna evidencia del cliente pueda moverlo. Es la trazabilidad:
    #: junto a `started_at` permite ver cuánto tardó una acción en sincronizar.
    started_received_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_received_at = Column(DateTime(timezone=True), nullable=True)

    #: De cuál de los dos relojes salió la hora de ocurrencia. Sin esta columna,
    #: una jornada cuya evidencia se rechazó por contradictoria sería
    #: indistinguible de una cuya evidencia se aceptó, y el sistema estaría
    #: afirmando una precisión que no tiene.
    started_at_source = Column(
        String(20),
        nullable=False,
        server_default=WorkSessionTimeSource.SERVER_RECEIPT.value,
    )
    ended_at_source = Column(String(20), nullable=True)

    #: Lo que el dispositivo reportó, **verbatim**, se acepte o se rechace. Si
    #: `*_at_source` dice `server_receipt` habiendo aquí un valor, esta columna
    #: es la evidencia de qué se descartó y por qué era descartable.
    start_device_captured_at = Column(DateTime(timezone=True), nullable=True)
    start_utc_offset_minutes = Column(Integer, nullable=True)
    end_device_captured_at = Column(DateTime(timezone=True), nullable=True)
    end_utc_offset_minutes = Column(Integer, nullable=True)

    #: Snapshot histórico. `NULL` en las dos columnas es un estado válido: un
    #: supervisor sin asignación de vehículo (§6.1). Nunca se reescribe tras la
    #: creación.
    vehicle_id = Column(Integer, nullable=True)
    mpg_snapshot = Column(Numeric(5, 2), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WorkSession id={self.id} user_id={self.user_id} "
            f"status={self.status} session_date={self.session_date}>"
        )
