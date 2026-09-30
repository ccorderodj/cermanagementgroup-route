"""Kilometraje oficial del viaje: estado y provenance (RTE06-CP3).

Dos tablas, y la segunda es la que importa a largo plazo
--------------------------------------------------------
`trip_mileage` es el resultado y su máquina de estados. `trip_mileage_segment`
es **por qué** ese resultado es ése: un tramo por pareja consecutiva de
waypoints, con las coordenadas que se enrutaron de verdad.

Por qué el segmento copia las coordenadas
-----------------------------------------
Porque §28 exige que un kilometraje `calculated` siga siendo explicable
**después** de que la evidencia de ubicación cruda se purgue algún día. Si el
segmento sólo guardara `location_fix_id`, el día del purgado el número quedaría
sin sustento: auditable hoy, inauditable mañana.

Así que la coordenada, el nivel de evidencia, la precisión y la hora de captura
se copian dentro del segmento en el momento del cálculo. `*_fix_id` se conserva
como **referencia blanda** —sin clave foránea— para poder investigar mientras la
evidencia exista. §28 lo permite expresamente: "raw fix IDs may be retained as
soft references, but must not be the only provenance".

No hay tabla de waypoints
-------------------------
El waypoint **es** el `location_fix` del evento correspondiente. Una tabla
aparte guardaría el mismo hecho dos veces (invariante 9), y la segunda copia
acabaría diciendo algo distinto. El orden sale de la ocurrencia:
`trip.started_at`, luego cada `trip_purpose_change.changed_at`, luego
`trip.arrived_at`.

Inmutabilidad sin disparador
----------------------------
§27 dice que un `calculated` no lo altera nada. Lo garantiza la forma de la
escritura, no un permiso: toda transición hace
`UPDATE ... WHERE state = 'pending_calculation'`, así que `rowcount == 0`
significa "ya era terminal" y no se toca. Es el mismo patrón que ya protege la
terminalización de actividades. Un disparador append-only aquí no serviría:
`trip_mileage` **tiene** que poder pasar de pendiente a terminal una vez.

`trip_mileage_segment` sí es append-only por disparador: un tramo calculado es
un hecho medido y no se reescribe. §25 lo exige al decir que no se descarte
provenance ya válida.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel


class MileageState(BusinessEnum):
    """Exactamente los cuatro estados de §24.

    `degraded` no está, y es deliberado: §24 dice que es metadato de calidad y
    **nunca** un estado de kilometraje. Vive en el nivel de evidencia de cada
    waypoint del segmento.
    """

    #: Transitorio. Queda un camino automático a la resolución.
    PENDING_CALCULATION = "pending_calculation"
    #: Terminal con éxito: todos los waypoints existen y todos los tramos
    #: dieron una distancia válida y plausible.
    CALCULATED = "calculated"
    #: Terminal por falta de evidencia: un waypoint requerido no existe.
    NOT_CALCULABLE = "not_calculable"
    #: Terminal por fallo de routing: la evidencia estaba, el proveedor no pudo.
    CALCULATION_FAILED = "calculation_failed"


class MileageTerminalReason(BusinessEnum):
    """Por qué terminó donde terminó. Verdad concreta, no una etiqueta vaga.

    §17 y §24 piden una razón terminal veraz. "No calculable" sin decir cuál de
    los waypoints faltaba obligaría a reconstruirlo a mano cada vez.
    """

    #: El waypoint de `Start Trip` no existe.
    START_WAYPOINT_MISSING = "start_waypoint_missing"
    #: El waypoint de `Arrived` no existe.
    ARRIVAL_WAYPOINT_MISSING = "arrival_waypoint_missing"
    #: Un `Change Plan` ocurrió y su waypoint quedó Missing (§17, caso C4).
    CHANGE_PLAN_WAYPOINT_MISSING = "change_plan_waypoint_missing"
    #: El viaje se interrumpió sin llegar (§19, caso L2).
    INTERRUPTED_WITHOUT_ARRIVAL = "interrupted_without_arrival"
    #: Todos los waypoints estaban; el routing agotó la contingencia.
    ROUTING_EXHAUSTED = "routing_exhausted"
    #: Un tramo devolvió una distancia que no pasó la plausibilidad, repetidas
    #: veces (§26, caso R4).
    IMPLAUSIBLE_SEGMENT = "implausible_segment"


class TripMileage(TimeStampedModel):
    """El kilometraje oficial de un viaje, y en qué punto está su cálculo."""

    __tablename__ = "trip_mileage"
    __table_args__ = (
        MileageState.check("state", name="ck_trip_mileage_state"),
        MileageTerminalReason.check(
            "terminal_reason", name="ck_trip_mileage_terminal_reason"
        ),
        # Un viaje, un kilometraje. Un trabajo de fondo duplicado no crea un
        # segundo hecho oficial (§27 "no duplicate job alters it").
        UniqueConstraint("trip_id", "company_id", name="uq_trip_mileage_trip"),
        # Para que el tramo pueda referenciarla con clave compuesta y no se
        # pueda colgar de un kilometraje de otro tenant.
        UniqueConstraint("id", "company_id", name="uq_trip_mileage_id_company"),
        ForeignKeyConstraint(
            ["trip_id", "company_id"],
            ["trip.id", "trip.company_id"],
            name="fk_trip_mileage_trip_same_company",
            ondelete="CASCADE",
        ),
        # `calculated` exige número y fecha de cálculo; los demás estados exigen
        # que **no** haya número. Un total publicado junto a un estado no
        # terminal sería el total parcial que §25 prohíbe enseñar como final.
        CheckConstraint(
            "(state = 'calculated' AND total_meters IS NOT NULL "
            " AND calculated_at IS NOT NULL AND terminal_reason IS NULL) "
            "OR (state <> 'calculated' AND total_meters IS NULL "
            " AND calculated_at IS NULL)",
            name="ck_trip_mileage_calculated_facts",
        ),
        # Los dos estados de excepción exigen decir por qué; pendiente no.
        CheckConstraint(
            "(state IN ('not_calculable', 'calculation_failed') "
            " AND terminal_reason IS NOT NULL) "
            "OR (state NOT IN ('not_calculable', 'calculation_failed') "
            " AND (state = 'calculated' OR terminal_reason IS NULL))",
            name="ck_trip_mileage_terminal_needs_reason",
        ),
        CheckConstraint(
            "total_meters IS NULL OR total_meters >= 0",
            name="ck_trip_mileage_total_non_negative",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_trip_mileage_attempts"),
        # El sweeper busca por aquí: pendientes cuyo reintento ya venció.
        Index(
            "ix_trip_mileage_due",
            "state",
            "next_attempt_at",
            postgresql_where=Column("state") == "pending_calculation",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id = Column(Integer, nullable=False)

    state = Column(
        String(30), nullable=False, server_default=MileageState.PENDING_CALCULATION.value
    )
    #: Metros. La unidad de almacenamiento es la que devuelve el proveedor, y la
    #: conversión a millas se hace al leer: guardar las dos sería guardar el
    #: mismo hecho dos veces, y redondearlo dos veces.
    total_meters = Column(Numeric(12, 2), nullable=True)
    calculated_at = Column(DateTime(timezone=True), nullable=True)
    terminal_reason = Column(String(40), nullable=True)

    #: Cuántas veces se ha intentado, y cuándo toca la siguiente. El reintento es
    #: acotado (§24: "no Trip may remain Pending indefinitely").
    attempt_count = Column(Integer, nullable=False, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    #: El último fallo, en texto, para diagnóstico. Sin coordenadas (§35).
    last_error = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<TripMileage trip={self.trip_id} {self.state}>"


class TripMileageSegment(TimeStampedModel):
    """Un tramo vial entre dos waypoints consecutivos, con todo lo que lo explica.

    Append-only: una vez medido, el tramo no se reescribe. Si hubiera que volver
    a calcular un viaje entero —cosa que §27 prohíbe para los `calculated`— sería
    con filas nuevas, nunca editando éstas.
    """

    __tablename__ = "trip_mileage_segment"
    __table_args__ = (
        UniqueConstraint(
            "trip_mileage_id", "sequence", name="uq_trip_mileage_segment_sequence"
        ),
        ForeignKeyConstraint(
            ["trip_mileage_id", "company_id"],
            ["trip_mileage.id", "trip_mileage.company_id"],
            name="fk_trip_mileage_segment_parent_same_company",
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence >= 1", name="ck_trip_mileage_segment_sequence"),
        CheckConstraint(
            "distance_meters >= 0", name="ck_trip_mileage_segment_distance"
        ),
        CheckConstraint(
            "from_latitude >= -90 AND from_latitude <= 90 "
            "AND to_latitude >= -90 AND to_latitude <= 90 "
            "AND from_longitude >= -180 AND from_longitude <= 180 "
            "AND to_longitude >= -180 AND to_longitude <= 180",
            name="ck_trip_mileage_segment_coordinates",
        ),
        # Sin índice propio sobre `(trip_mileage_id, sequence)`:
        # `uq_trip_mileage_segment_sequence` ya lo indexa por ser único. El
        # autogenerate lo proponía igualmente, y es el mismo duplicado que 0008
        # tuvo que quitar a mano.
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_mileage_id = Column(Integer, nullable=False)
    #: 1, 2, 3… en el orden de los waypoints. Es lo que permite auditar
    #: "waypoint order" (§23) sin recalcularlo desde las horas.
    sequence = Column(Integer, nullable=False)

    # ── El origen del tramo, copiado ───────────────────────────────────────
    from_event_kind = Column(String(30), nullable=False)
    from_latitude = Column(Numeric(9, 6), nullable=False)
    from_longitude = Column(Numeric(10, 7), nullable=False)
    from_evidence_level = Column(String(20), nullable=False)
    from_accuracy_m = Column(Numeric(10, 2), nullable=True)
    from_captured_at = Column(DateTime(timezone=True), nullable=False)
    #: Referencia blanda al `location_fix`. Sin FK a propósito: un purgado
    #: futuro de evidencia cruda no puede borrar ni bloquear este tramo (§28).
    from_fix_id = Column(Integer, nullable=True)

    # ── El destino del tramo, copiado ──────────────────────────────────────
    to_event_kind = Column(String(30), nullable=False)
    to_latitude = Column(Numeric(9, 6), nullable=False)
    to_longitude = Column(Numeric(10, 7), nullable=False)
    to_evidence_level = Column(String(20), nullable=False)
    to_accuracy_m = Column(Numeric(10, 2), nullable=True)
    to_captured_at = Column(DateTime(timezone=True), nullable=False)
    to_fix_id = Column(Integer, nullable=True)

    # ── El resultado y quién lo produjo ────────────────────────────────────
    distance_meters = Column(Numeric(12, 2), nullable=False)
    provider = Column(String(40), nullable=False)
    method = Column(String(40), nullable=False)
    provider_version = Column(String(40), nullable=True)
    computed_at = Column(DateTime(timezone=True), nullable=False)
    #: Distancia en línea recta, sólo como diagnóstico. §26 permite usar
    #: Haversine internamente para comparar y **prohíbe** publicarlo como
    #: kilometraje: guardarlo aquí, junto al de verdad, deja ver la relación
    #: entre los dos sin que nadie pueda confundirlos.
    haversine_meters = Column(Numeric(12, 2), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TripMileageSegment {self.trip_mileage_id}#{self.sequence} "
            f"{self.distance_meters}m>"
        )
