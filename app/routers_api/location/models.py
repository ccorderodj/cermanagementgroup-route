"""Evidencia de ubicación de los eventos del ciclo de vida (RTE06-CP2).

Dos tablas y una tupla
----------------------
`location_fix` guarda un punto. `missing_location_event` guarda la ausencia de
uno. No son la misma tabla con un campo distinto a propósito: §11 de la
instrucción dice que `missing` **no** es un nivel de evidencia, y meterlo como
tal obligaría a que cada consulta de kilometraje recordara excluirlo.

Las dos se correlacionan igual, con una tupla en vez de una tabla nueva:

    (company_id, event_kind, subject_kind, subject_id)

Por qué esa tupla y no un identificador propio
-----------------------------------------------
§14 exige correlación con **la acción exacta** que causó la captura, y prohíbe
correlacionar por proximidad de tiempo. Los sujetos ya existen y ya son
durables:

    start_work, end_work             → work_session.id
    start_trip, arrived             → trip.id
    change_plan                     → trip_purpose_change.id
    activity_complete, leave        → activity_execution.id

`trip_purpose_change` ya tiene id propio y `changed_at`, así que varios
`Change Plan` del mismo viaje quedan **independientes y ordenados** sin inventar
nada — que es justo lo que §32 pide conservar a través del offline.

La otra opción era la clave de idempotencia de la acción, y no sirve: el
scheduler purga `idempotency_record` cada hora (`IDEMPOTENCY_TTL_HOURS`), y esta
evidencia tiene que sobrevivir años. La clave se sigue usando para que un reenvío
no escriba dos veces; no es la identidad del evento.

Append-only
-----------
Las dos tablas están en `APPEND_ONLY_TABLES`, así que un disparador rechaza
`UPDATE` y `DELETE`. Una coordenada capturada es un hecho observado: corregirla
no es editarla, y si hiciera falta dejar constancia de otra cosa se añade una
fila. §35 lo pide explícitamente para la evidencia de ubicación.

Coordenadas en `Numeric`, no en `float`
---------------------------------------
Este dato acaba en dinero: el kilometraje alimenta la estimación de combustible.
`double precision` reintroduciría ruido de redondeo en la provenance que §28
obliga a poder auditar después de purgar la evidencia cruda. `Numeric(9,6)` y
`Numeric(10,7)` dan ~11 cm, que sobra para routing vial.
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
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel


class LocationEventKind(BusinessEnum):
    """Los siete eventos que intentan capturar ubicación (§10).

    `start_activity` **no** está, y su ausencia es una decisión de la
    instrucción: §10 dice expresamente que no se añada una captura obligatoria
    ahí.
    """

    START_WORK = "start_work"
    START_TRIP = "start_trip"
    CHANGE_PLAN = "change_plan"
    ARRIVED = "arrived"
    ACTIVITY_COMPLETE = "activity_complete"
    ACTIVITY_LEAVE = "activity_leave"
    END_WORK = "end_work"


class LocationSubjectKind(BusinessEnum):
    """A qué fila de dominio se ancla la correlación."""

    WORK_SESSION = "work_session"
    TRIP = "trip"
    TRIP_PURPOSE_CHANGE = "trip_purpose_change"
    ACTIVITY_EXECUTION = "activity_execution"


class LocationEvidenceLevel(BusinessEnum):
    """Exactamente tres niveles (§11).

    `missing` no está aquí, y no por olvido: la ausencia de punto se registra en
    `missing_location_event`. Meterla como cuarto nivel haría que cualquier
    consulta que pida waypoints tuviera que acordarse de excluirla, y la que se
    olvidara calcularía kilometraje con una coordenada que no existe.
    """

    FRESH = "fresh"
    DEGRADED_CACHED = "degraded_cached"
    RECOVERED = "recovered"


class LocationPermissionState(BusinessEnum):
    """Lo que el navegador dijo, sin interpretarlo.

    §29 prohíbe inventar causas que la plataforma no puede demostrar —"el GPS
    está apagado"—, así que esto es sólo el estado del permiso tal como lo
    reporta la Permissions API, más `unavailable` para cuando no la hay.
    """

    GRANTED = "granted"
    DENIED = "denied"
    PROMPT = "prompt"
    UNAVAILABLE = "unavailable"


class MissingNotificationStatus(BusinessEnum):
    """Si el aviso de §30 ya salió.

    RTE06 **persiste** el estado y expone el contrato; no entrega el aviso ni
    construye un buzón dentro de Route, que es lo que §30 prohíbe.
    """

    PENDING = "pending"
    NOTIFIED = "notified"
    SUPPRESSED = "suppressed"


class MissingLocationReason(BusinessEnum):
    """Por qué no hay punto. Hechos observables, nada más (§29)."""

    #: El permiso fue denegado y no había punto cacheado aceptable.
    PERMISSION_DENIED = "permission_denied"
    #: La plataforma respondió con error de posición.
    POSITION_UNAVAILABLE = "position_unavailable"
    #: Se agotó el tiempo de adquisición en todas las etapas.
    ACQUISITION_TIMEOUT = "acquisition_timeout"
    #: Había punto cacheado pero no cumplía frescura/precisión.
    CACHED_REJECTED = "cached_rejected"
    #: La ventana de recuperación terminó sin punto y sin más información.
    RECOVERY_WINDOW_EXHAUSTED = "recovery_window_exhausted"
    #: El cliente nunca volvió a decir nada y lo cerró el sweeper.
    NO_CLIENT_REPORT = "no_client_report"


#: Ligadura de un evento a su sujeto. Un `change_plan` no puede colgar de un
#: `work_session`: sería una correlación imposible de reconstruir después.
_SUJETO_POR_EVENTO: dict[LocationEventKind, LocationSubjectKind] = {
    LocationEventKind.START_WORK: LocationSubjectKind.WORK_SESSION,
    LocationEventKind.END_WORK: LocationSubjectKind.WORK_SESSION,
    LocationEventKind.START_TRIP: LocationSubjectKind.TRIP,
    LocationEventKind.ARRIVED: LocationSubjectKind.TRIP,
    LocationEventKind.CHANGE_PLAN: LocationSubjectKind.TRIP_PURPOSE_CHANGE,
    LocationEventKind.ACTIVITY_COMPLETE: LocationSubjectKind.ACTIVITY_EXECUTION,
    LocationEventKind.ACTIVITY_LEAVE: LocationSubjectKind.ACTIVITY_EXECUTION,
}


def subject_kind_for(event_kind: LocationEventKind) -> LocationSubjectKind:
    """Qué tabla es el sujeto de este evento. Una sola respuesta, en un sitio."""
    return _SUJETO_POR_EVENTO[event_kind]


def _check_pareja_evento_sujeto(name: str) -> CheckConstraint:
    """`CHECK` que sólo admite las parejas de `_SUJETO_POR_EVENTO`.

    Se deriva del diccionario para que añadir un evento no deje la restricción
    atrás — el mismo motivo por el que `BusinessEnum` deriva su `CHECK`.
    """
    parejas = " OR ".join(
        f"(event_kind = '{evento.value}' AND subject_kind = '{sujeto.value}')"
        for evento, sujeto in _SUJETO_POR_EVENTO.items()
    )
    return CheckConstraint(parejas, name=name)


#: Rango válido de coordenadas. §31 pide validarlo, y se valida **también** aquí:
#: el schema protege la API, la restricción protege la tabla (invariante 6).
_COORDENADAS_VALIDAS = (
    "latitude >= -90 AND latitude <= 90 AND longitude >= -180 AND longitude <= 180"
)


class LocationFix(TimeStampedModel):
    """Un punto de ubicación atado a la acción exacta que lo causó.

    Lo que **no** guarda: nada que permita reconstruir el recorrido entre
    eventos. Son siete puntos por jornada como máximo más uno por cambio de
    plan, no una traza. §21 deja los breadcrumbs como opcionales y esta base no
    los implementa.
    """

    __tablename__ = "location_fix"
    __table_args__ = (
        LocationEventKind.check("event_kind", name="ck_location_fix_event_kind"),
        LocationSubjectKind.check("subject_kind", name="ck_location_fix_subject_kind"),
        LocationEvidenceLevel.check(
            "evidence_level", name="ck_location_fix_evidence_level"
        ),
        _check_pareja_evento_sujeto("ck_location_fix_event_subject"),
        CheckConstraint(_COORDENADAS_VALIDAS, name="ck_location_fix_coordinates"),
        CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0", name="ck_location_fix_accuracy"
        ),
        # Un punto `fresh` con edad declarada es una contradicción: o se acaba de
        # medir o viene de la caché. Y uno `degraded_cached` sin edad no se
        # puede auditar — §28 exige saber de cuándo era la coordenada usada.
        CheckConstraint(
            "(evidence_level = 'degraded_cached' AND source_age_seconds IS NOT NULL) "
            "OR (evidence_level <> 'degraded_cached' AND source_age_seconds IS NULL)",
            name="ck_location_fix_cached_age",
        ),
        CheckConstraint("subject_id > 0", name="ck_location_fix_subject_id"),
        # La jornada dueña, del mismo tenant. Compuesta igual que en `trip`:
        # referenciar una jornada de otra compañía es imposible por
        # construcción, no por cuidado de quien escriba el servicio.
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_location_fix_session_same_company",
            ondelete="CASCADE",
        ),
        Index(
            # **La correlación.** Un evento del ciclo de vida tiene como máximo
            # un punto autoritativo, y esto es lo que hace idempotente el
            # reenvío de la cola offline (§32, caso C6).
            "uq_location_fix_event",
            "company_id",
            "event_kind",
            "subject_kind",
            "subject_id",
            unique=True,
        ),
        Index("ix_location_fix_session", "company_id", "work_session_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        # Sin `index=True`: la columna va primera en los índices compuestos de
        # esta tabla, que ya la cubren. Un índice de un campo que es prefijo de
        # otro no protege nada y encarece cada escritura.
    )

    #: La jornada durante la que se capturó. §13 sólo permite capturar mientras
    #: está ACTIVE, y esta columna es lo que hace comprobable esa frontera.
    work_session_id = Column(Integer, nullable=False)

    event_kind = Column(String(30), nullable=False)
    subject_kind = Column(String(30), nullable=False)
    subject_id = Column(Integer, nullable=False)

    evidence_level = Column(String(20), nullable=False)
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    #: Radio de incertidumbre en metros, como lo da la plataforma. `NULL` cuando
    #: no lo dio: inventarlo sería fabricar precisión.
    accuracy_m = Column(Numeric(10, 2), nullable=True)

    #: Cuándo se **midió** el punto, según el dispositivo. Es la hora que manda:
    #: un punto cacheado no pasa a ser fresco porque se suba más tarde (§32).
    device_captured_at = Column(DateTime(timezone=True), nullable=False)
    #: Cuándo llegó al servidor. Las dos juntas dicen cuánto tardó en sincronizar.
    server_received_at = Column(DateTime(timezone=True), nullable=False)
    #: Edad del punto cacheado en el momento de usarlo. Sólo para
    #: `degraded_cached`; el `CHECK` de arriba lo garantiza.
    source_age_seconds = Column(Integer, nullable=True)

    permission_state = Column(String(20), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<LocationFix {self.event_kind}/{self.subject_id} "
            f"{self.evidence_level}>"
        )


class MissingLocationEvent(TimeStampedModel):
    """La ausencia de punto para un evento que **sí ocurrió** (§29).

    Nunca se crea para un evento que no pasó: §19 lo dice de `Arrived` en un
    viaje interrumpido, y la regla vale en general. Esta fila significa "esto
    ocurrió y no pudimos situarlo", no "esto no ocurrió".
    """

    __tablename__ = "missing_location_event"
    __table_args__ = (
        LocationEventKind.check("event_kind", name="ck_missing_location_event_kind"),
        LocationSubjectKind.check(
            "subject_kind", name="ck_missing_location_subject_kind"
        ),
        MissingLocationReason.check("reason_code", name="ck_missing_location_reason"),
        MissingNotificationStatus.check(
            "notification_status", name="ck_missing_location_notification"
        ),
        _check_pareja_evento_sujeto("ck_missing_location_event_subject"),
        CheckConstraint("subject_id > 0", name="ck_missing_location_subject_id"),
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_missing_location_session_same_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["trip_id", "company_id"],
            ["trip.id", "trip.company_id"],
            name="fk_missing_location_trip_same_company",
            ondelete="CASCADE",
        ),
        Index(
            # Uno por evento. El caso G5 pide "exactamente un evento", y con esto
            # lo garantiza la base y no el cuidado de quien llame.
            "uq_missing_location_event",
            "company_id",
            "event_kind",
            "subject_kind",
            "subject_id",
            unique=True,
        ),
        Index(
            "ix_missing_location_pending_notice",
            "company_id",
            "notification_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        # Sin `index=True`: la columna va primera en los índices compuestos de
        # esta tabla, que ya la cubren. Un índice de un campo que es prefijo de
        # otro no protege nada y encarece cada escritura.
    )

    work_session_id = Column(Integer, nullable=False)
    #: El viaje, cuando el evento pertenece a uno. `NULL` en `start_work` y
    #: `end_work`, que no cuelgan de ningún viaje.
    trip_id = Column(Integer, nullable=True)

    event_kind = Column(String(30), nullable=False)
    subject_kind = Column(String(30), nullable=False)
    subject_id = Column(Integer, nullable=False)

    #: Cuándo ocurrió **el evento operativo**, no cuándo se dio por perdido.
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    reason_code = Column(String(40), nullable=False)

    #: Qué se intentó, en crudo: etapas, errores y tiempos que el cliente
    #: reportó. Es lo que permite investigar sin tener que creerse el
    #: `reason_code` (§29 "acquisition attempt evidence").
    attempts = Column(JSONB, nullable=False, server_default="[]")
    permission_state = Column(String(20), nullable=True)
    #: Metadatos del último punto conocido **rechazado**, si hubo alguno: su edad
    #: y su precisión, nunca sus coordenadas. Saber que existía un punto de hace
    #: dos horas con 3 km de error explica el fallo; guardar dónde estaba sería
    #: conservar una ubicación que el sistema decidió no usar.
    rejected_candidate = Column(JSONB, nullable=True)

    #: Estado de aviso. §30 pide persistirlo y exponer un contrato limpio, sin
    #: construir una plataforma de notificaciones dentro de Route.
    notification_status = Column(String(20), nullable=False, server_default="pending")
    notified_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MissingLocationEvent {self.event_kind}/{self.subject_id} "
            f"{self.reason_code}>"
        )
