"""
Evidencia de odómetro (RTE04-C3/C4).

Qué es y qué **no** es
-----------------------
Es evidencia de la jornada y su vehículo: una lectura confirmada por el
supervisor, respaldada por una foto. **No es millaje oficial.** El millaje de
ruta —el hecho oficial de distancia por carretera— es un dominio futuro y
distinto; nada de aquí lo alimenta, lo sustituye ni lo corrige. La distancia
que se deriva de dos lecturas se llama *Odometer Distance* y nunca `Miles` a
secas, precisamente para que no se confundan.

Tres estados y dos caminos
---------------------------
```
PENDING ──foto + confirmación──────────────────────────▶ PHOTO_CONFIRMED
   │
   ├──sin foto posible──▶ EXCEPTION_REQUESTED ──Admin aprueba──▶ EXCEPTION_APPROVED
   │                                │                                   │
   │                                └──Admin rechaza──▶ vuelve a PENDING │
   │                                                                     ▼
   │                                                    MANUAL_EXCEPTION_CONFIRMED
   └──no aplica vehículo──▶ NOT_REQUIRED
```

`NOT_REQUIRED` existe para no fabricar una lectura cuando no hay vehículo de
jornada: es una respuesta honesta, no un cero inventado.

Por qué los metadatos del fichero viven aquí
---------------------------------------------
El repositorio tiene primitivas de almacenamiento —proveedor, validación de
medios, escáner— pero **no** un registro de ficheros ni ningún dominio que lo
consuma: RTE04 es el primero. Crear un registro genérico de plataforma para un
solo consumidor sería meter un dominio nuevo en el núcleo, que las reglas del
repositorio y la propia resolución 003 prohíben. Así que la clave de
almacenamiento y la huella del contenido se guardan en la fila de evidencia.
"""

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
    text,
)

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin


class OdometerEvidenceType(BusinessEnum):
    """Los dos extremos de la jornada. Una aprobación para uno no sirve al otro."""

    START = "start"
    END = "end"


class OdometerStatus(BusinessEnum):
    PENDING = "pending"
    PHOTO_CONFIRMED = "photo_confirmed"
    EXCEPTION_REQUESTED = "exception_requested"
    EXCEPTION_APPROVED = "exception_approved"
    MANUAL_EXCEPTION_CONFIRMED = "manual_exception_confirmed"
    NOT_REQUIRED = "not_required"


#: Estados que satisfacen la guarda de `Start Trip`. Sólo estos tres: una
#: excepción *aprobada* todavía no es una lectura, así que no desbloquea nada
#: hasta que el supervisor la confirme.
RESOLVED_STATUSES = (
    OdometerStatus.PHOTO_CONFIRMED.value,
    OdometerStatus.MANUAL_EXCEPTION_CONFIRMED.value,
    OdometerStatus.NOT_REQUIRED.value,
)


class OdometerEvidenceMethod(BusinessEnum):
    """Cómo se obtuvo la lectura. **Nunca se disfraza una de la otra.**

    `MANUAL_NO_PHOTO` queda marcado para siempre: una lectura sin foto no puede
    parecer evidencia fotográfica después, por mucho que un administrador la
    haya autorizado.
    """

    PHOTO = "photo"
    MANUAL_NO_PHOTO = "manual_no_photo"


class OdometerEvidence(TimeStampedModel, VersionedMixin):
    """La lectura de un extremo de la jornada, con su procedencia.

    Una fila por jornada y tipo, garantizado por `uq_odometer_evidence_session_type`:
    no hay dos lecturas de inicio compitiendo por ser la buena.

    La sugerencia del OCR y la lectura confirmada se guardan **por separado**
    cuando ambas existen. El OCR nunca establece por sí solo un hecho de
    millaje: es una ayuda para teclear menos, y la autoridad es la confirmación
    del supervisor. Guardar sólo el valor final borraría la diferencia entre
    "lo leyó la máquina" y "lo confirmó una persona".

    El vehículo es el de la **instantánea de la jornada**, no el que el
    supervisor tenga asignado hoy: si el administrador reasigna después, esta
    evidencia sigue hablando del vehículo con el que se condujo.
    """

    __tablename__ = "odometer_evidence"
    __table_args__ = (
        OdometerEvidenceType.check("evidence_type", name="ck_odometer_evidence_type"),
        OdometerStatus.check("status", name="ck_odometer_evidence_status"),
        OdometerEvidenceMethod.check(
            "evidence_method", name="ck_odometer_evidence_method"
        ),
        UniqueConstraint("id", "company_id", name="uq_odometer_evidence_id_company"),
        UniqueConstraint(
            "work_session_id",
            "evidence_type",
            name="uq_odometer_evidence_session_type",
        ),
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_odometer_evidence_session_same_company",
            ondelete="CASCADE",
        ),
        # `RESTRICT`: borrar un vehículo del maestro no puede llevarse por
        # delante la evidencia de lo que se condujo con él. RTE02-A01 dejó esos
        # borrados como lápida, así que la fila sigue resolviendo.
        ForeignKeyConstraint(
            ["vehicle_id", "company_id"],
            ["vehicle.id", "vehicle.company_id"],
            name="fk_odometer_evidence_vehicle_same_company",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "confirmed_reading IS NULL OR confirmed_reading >= 0",
            name="ck_odometer_reading_not_negative",
        ),
        Index(
            "ix_odometer_evidence_session",
            "company_id",
            "work_session_id",
            "evidence_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_session_id = Column(Integer, nullable=False, index=True)
    #: El vehículo de la instantánea de la jornada. `NULL` cuando no aplica
    #: ninguno, que es el caso de `NOT_REQUIRED`.
    vehicle_id = Column(Integer, nullable=True)

    evidence_type = Column(String(10), nullable=False)
    status = Column(
        String(30), nullable=False, server_default=OdometerStatus.PENDING.value
    )
    evidence_method = Column(String(20), nullable=True)

    #: Lo que confirmó el supervisor. La autoridad.
    confirmed_reading = Column(Numeric(10, 1), nullable=True)
    #: Lo que sugirió el OCR, si sugirió algo. **Nunca** sustituye a la anterior.
    ocr_detected_reading = Column(Numeric(10, 1), nullable=True)

    #: Metadatos del fichero privado. Sin URL pública: se sirve por un endpoint
    #: autorizado que comprueba tenant y propiedad en cada lectura.
    storage_key = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    content_type = Column(String(100), nullable=True)
    byte_size = Column(Integer, nullable=True)

    captured_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by = Column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<OdometerEvidence session={self.work_session_id} "
            f"type={self.evidence_type} status={self.status}>"
        )


class OdometerExceptionStatus(BusinessEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"


class OdometerExceptionReason(BusinessEnum):
    """Los cuatro motivos aprobados. Cerrados a propósito.

    Un campo libre convertiría la excepción en un permiso permanente disfrazado:
    cualquiera escribiría cualquier cosa y nadie podría revisar el patrón.
    """

    CAMERA_UNAVAILABLE = "camera_unavailable"
    PERMISSION_PROBLEM = "permission_problem"
    NO_USABLE_PHOTO = "no_usable_photo"
    OTHER = "other"


class OdometerExceptionRequest(TimeStampedModel, VersionedMixin):
    """Permiso de un solo uso para teclear una lectura sin foto.

    Acotado a **exactamente** un tenant, un supervisor, una jornada, un
    vehículo y un extremo (`START` o `END`). Una aprobación de inicio no
    autoriza el cierre, y la de un día no sirve para otro: el alcance vive en
    las columnas, no en la confianza.

    `CONSUMED` es lo que hace que sea de un solo uso. Aprobada y usada, la
    siguiente vez hay que volver a pedirla.

    No es una capacidad de rol: dar permiso permanente para teclear lecturas
    vaciaría de sentido la evidencia fotográfica, y la instrucción lo prohíbe
    de forma explícita.
    """

    __tablename__ = "odometer_exception_request"
    __table_args__ = (
        OdometerEvidenceType.check(
            "evidence_type", name="ck_odometer_exception_type"
        ),
        OdometerExceptionStatus.check("status", name="ck_odometer_exception_status"),
        OdometerExceptionReason.check("reason", name="ck_odometer_exception_reason"),
        UniqueConstraint("id", "company_id", name="uq_odometer_exception_id_company"),
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_odometer_exception_session_same_company",
            ondelete="CASCADE",
        ),
        # Una sola solicitud viva por jornada y extremo: pedirla dos veces no
        # abre dos puertas.
        Index(
            "uq_odometer_exception_open",
            "company_id",
            "work_session_id",
            "evidence_type",
            unique=True,
            postgresql_where=text("status IN ('requested', 'approved')"),
        ),
        Index(
            "ix_odometer_exception_pending",
            "company_id",
            "status",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_session_id = Column(Integer, nullable=False, index=True)
    vehicle_id = Column(Integer, nullable=True)
    evidence_type = Column(String(10), nullable=False)

    status = Column(
        String(20), nullable=False, server_default=OdometerExceptionStatus.REQUESTED.value
    )
    reason = Column(String(30), nullable=False)
    #: Aclaración opcional del supervisor. No sustituye al motivo cerrado.
    reason_note = Column(Text, nullable=True)

    requested_by = Column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at = Column(DateTime(timezone=True), nullable=False)
    #: Quién decidió y cuándo. `NULL` mientras nadie ha decidido.
    decided_by = Column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True
    )
    decided_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<OdometerExceptionRequest session={self.work_session_id} "
            f"type={self.evidence_type} status={self.status}>"
        )
