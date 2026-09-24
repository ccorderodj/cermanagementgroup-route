"""
El viaje del supervisor dentro de su jornada (RTE04).

Tres conceptos que el producto distingue y que este módulo **no** colapsa:

* **Work Session** — la jornada (RTE03).
* **Trip** — un desplazamiento real dentro de esa jornada.
* **Activity** — lo que se ejecuta *después* de llegar. No existe todavía: es
  RTE05, y aquí se deja el punto de extensión sin simularlo.

Propósito no es Actividad
--------------------------
El propósito responde **por qué se mueve** el supervisor; la actividad, **qué
hizo al llegar**. Son campos distintos, en tablas distintas, en momentos
distintos del flujo. Mezclarlos es el error que el baseline de RTE01 señala de
forma explícita, y por eso los siete contextos son un `BusinessEnum` del
producto y no una lista configurable por el tenant: un tenant no inventa
motivos de desplazamiento.

Lo que este módulo deliberadamente NO hace
-------------------------------------------
No calcula millaje, no captura GPS, no crea bloques de actividad y no cierra
solo un viaje operativo al llegar. Un viaje operativo se queda en `ARRIVED`
esperando a RTE05; fabricar su cierre sería simular una funcionalidad que no
está construida.
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
    text,
)

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin


class TripPurpose(BusinessEnum):
    """Los siete contextos del producto. Cerrados: los define CER, no el tenant.

    `HOME` es especial y termina distinto que los demás: al llegar cierra el
    viaje directamente, sin bloque de actividad, porque volver a casa no es una
    parada operativa donde se ejecute nada.
    """

    CLIENT_VISIT = "client_visit"
    RECRUITING = "recruiting"
    EMPLOYEE_VISIT = "employee_visit"
    CHECK_DELIVERY = "check_delivery"
    OFFICE = "office"
    OTHER = "other"
    HOME = "home"


class TripStatus(BusinessEnum):
    """`PLANNING → IN_TRANSIT → ARRIVED`, con dos salidas terminales.

    * `CLOSED` — lo alcanza un viaje `HOME` al llegar, y lo alcanzará un viaje
      operativo cuando RTE05 complete su bloque de actividad.
    * `INTERRUPTED` — lo alcanza un viaje en tránsito cuando el supervisor
      pulsa explícitamente `End Work Anyway`. **No se fabrica una llegada**: el
      viaje se interrumpe, que es lo que de verdad pasó.
    """

    PLANNING = "planning"
    IN_TRANSIT = "in_transit"
    ARRIVED = "arrived"
    CLOSED = "closed"
    INTERRUPTED = "interrupted"


#: Estados desde los que el viaje ya no puede avanzar. Se usan para el índice
#: parcial que garantiza un solo viaje vivo por jornada, y para decidir si una
#: transición es legal. `ARRIVED` **no** está aquí: un viaje operativo que llegó
#: sigue vivo, esperando a RTE05.
TERMINAL_STATUSES = (TripStatus.CLOSED.value, TripStatus.INTERRUPTED.value)


class Trip(TimeStampedModel, VersionedMixin):
    """Un desplazamiento real, dentro de una jornada `ACTIVE`.

    Un solo viaje vivo por jornada, garantizado por la base
    -------------------------------------------------------
    `uq_trip_one_non_terminal` es un índice único **parcial** sobre los estados
    no terminales: un supervisor no puede tener dos viajes abiertos a la vez.
    Comprobarlo en Python protege mientras nadie se olvide y mientras no haya
    concurrencia real; comprobarlo en la base protege siempre (invariante 6).

    El plan original no se pisa nunca
    ----------------------------------
    `original_purpose` y `original_context_reference` se escriben una vez, al
    crear el viaje, y ningún camino de este módulo los vuelve a tocar.
    `current_purpose` refleja el último cambio válido, y cada cambio deja una
    fila en `trip_purpose_change`. Así se puede responder después qué pensaba
    hacer el supervisor, qué cambió por el camino y dónde acabó — que es lo que
    el producto llama trazabilidad de `Change Plan`.

    Dos relojes, igual que en la jornada
    -------------------------------------
    Cada transición guarda **cuándo ocurrió** y **cuándo se recibió**, con la
    misma semántica que fijó el cierre de RTE03: una acción encolada sin
    cobertura ocurrió cuando el supervisor la pulsó, no cuando el servidor se
    enteró. Ver `app/routers_api/worksessions/models.py`.

    El campo de texto libre
    ------------------------
    Cada contexto tiene **un** dato de referencia y es **texto libre** por
    decisión de CER: destino del cliente, área de reclutamiento, referencia del
    empleado, oficina, área de "Other". No se convierte en catálogo — eso sería
    reintroducir justo lo que CER quitó.

    El valor estandarizado de cada contexto **no está aquí**, y es deliberado:
    el baseline no determina si se elige antes de salir o al llegar, así que
    ubicarlo habría sido inventar el flujo. Queda reportado como decisión
    pendiente de CER (ver el informe de entrega de RTE04).
    """

    __tablename__ = "trip"
    __table_args__ = (
        TripStatus.check("status", name="ck_trip_status"),
        TripPurpose.check("original_purpose", name="ck_trip_original_purpose"),
        TripPurpose.check("current_purpose", name="ck_trip_current_purpose"),
        UniqueConstraint("id", "company_id", name="uq_trip_id_company"),
        # Diana de la FK compuesta y garantía de aislamiento: un viaje no puede
        # colgar de la jornada de otro tenant aunque el servicio se equivoque.
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_trip_work_session_same_company",
            ondelete="CASCADE",
        ),
        # Un solo viaje vivo por jornada. Parcial a propósito: los terminados
        # pueden repetirse cuantas veces haga falta en el mismo día.
        Index(
            "uq_trip_one_non_terminal",
            "company_id",
            "work_session_id",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('closed', 'interrupted')"
            ),
        ),
        UniqueConstraint(
            "work_session_id", "sequence", name="uq_trip_session_sequence"
        ),
        CheckConstraint("sequence >= 1", name="ck_trip_sequence_positive"),
        # Ningún viaje puede llegar antes de salir.
        CheckConstraint(
            "arrived_at IS NULL OR started_at IS NULL OR arrived_at >= started_at",
            name="ck_trip_arrived_after_started",
        ),
        Index("ix_trip_company_session", "company_id", "work_session_id", "sequence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: La jornada dueña. El supervisor se deriva de ella: no se copia aquí, que
    #: sería una segunda respuesta para la misma pregunta (invariante 9).
    work_session_id = Column(Integer, nullable=False, index=True)

    #: Orden del viaje dentro de la jornada, empezando en 1.
    sequence = Column(Integer, nullable=False)

    status = Column(
        String(20), nullable=False, server_default=TripStatus.PLANNING.value
    )

    #: Lo que el supervisor dijo que iba a hacer. **Inmutable.**
    original_purpose = Column(String(30), nullable=False)
    original_context_reference = Column(Text, nullable=True)

    #: Lo que vale ahora, tras los cambios de plan que haya habido.
    current_purpose = Column(String(30), nullable=False)
    current_context_reference = Column(Text, nullable=True)

    #: Ocurrencia y recepción de cada transición (semántica de RTE03).
    started_at = Column(DateTime(timezone=True), nullable=True)
    started_received_at = Column(DateTime(timezone=True), nullable=True)
    arrived_at = Column(DateTime(timezone=True), nullable=True)
    arrived_received_at = Column(DateTime(timezone=True), nullable=True)
    #: Cuándo alcanzó un estado terminal, sea `CLOSED` o `INTERRUPTED`.
    ended_at = Column(DateTime(timezone=True), nullable=True)
    ended_received_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Trip id={self.id} session={self.work_session_id} "
            f"seq={self.sequence} status={self.status} "
            f"purpose={self.current_purpose}>"
        )


class TripPurposeChange(TimeStampedModel):
    """Cada `Change Plan`, apilado. Nunca se reescribe una fila anterior.

    Es la evidencia de que el plan cambió por el camino. Guarda de qué a qué,
    quién y cuándo, para poder reconstruir después la secuencia completa:
    plan original → cambios intermedios → plan final.

    No es append-only por disparador como `audit_event`, pero ningún camino de
    este módulo actualiza ni borra filas: la trazabilidad se consigue añadiendo,
    igual que en `vehicle_assignment`.
    """

    __tablename__ = "trip_purpose_change"
    __table_args__ = (
        TripPurpose.check("from_purpose", name="ck_trip_purpose_change_from"),
        TripPurpose.check("to_purpose", name="ck_trip_purpose_change_to"),
        ForeignKeyConstraint(
            ["trip_id", "company_id"],
            ["trip.id", "trip.company_id"],
            name="fk_trip_purpose_change_trip_same_company",
            ondelete="CASCADE",
        ),
        Index(
            "ix_trip_purpose_change_trip",
            "company_id",
            "trip_id",
            "changed_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id = Column(Integer, nullable=False, index=True)

    from_purpose = Column(String(30), nullable=False)
    from_context_reference = Column(Text, nullable=True)
    to_purpose = Column(String(30), nullable=False)
    to_context_reference = Column(Text, nullable=True)

    #: Cuándo lo cambió el supervisor, con la semántica de ocurrencia de RTE03.
    changed_at = Column(DateTime(timezone=True), nullable=False)
    changed_received_at = Column(DateTime(timezone=True), nullable=False)
    #: Quién. Es el usuario del núcleo, igual que en `work_session`.
    changed_by = Column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<TripPurposeChange trip={self.trip_id} "
            f"{self.from_purpose}->{self.to_purpose}>"
        )
