"""
Configuración de los correos de actividad (RTE-NOT-01): plantillas y
destinatarios, por compañía.

Sólo configuración. Ninguna de estas tablas envía nada: el motor que lea esto y
mande correos es RTE-NOT-02/03, y tendrá que volver a comprobar la elegibilidad
en el momento de enviar (BR-05).

Plantillas: una fila sólo si alguien la personalizó
---------------------------------------------------
El texto aprobado vive en `content.SPECS`. Una compañía sin fila usa ese texto;
la fila aparece al guardar o restaurar por primera vez. Así una compañía nueva
tiene las dos plantillas desde el primer momento sin sembrar nada, y la
migración no escribe datos de nadie.

Destinatarios: una fila por persona, ambos interruptores apagados
-----------------------------------------------------------------
`(user_id, company_id)` es una clave foránea **compuesta** a la pertenencia: la
base rechaza una preferencia para alguien que no es de esta compañía, sin
depender de que el servicio lo compruebe (BR-02). Los dos interruptores nacen en
`false` en la base, así que ninguna inserción olvidadiza suscribe a nadie
(BR-04). No hay columna de correo: la dirección sale siempre de la cuenta.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
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

from sqlalchemy.dialects.postgresql import JSONB

from app.core.enums import BusinessEnum
from app.database import Base
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin
from app.routers_api.activityemails.content import BODY_MAX, SUBJECT_MAX, ActivityEmailType


class ActivityEmailTemplate(TimeStampedModel, VersionedMixin):
    """El texto personalizado de un correo de actividad en una compañía."""

    __tablename__ = "activity_email_template"
    __table_args__ = (
        UniqueConstraint("company_id", "template_type", name="uq_activity_email_template_company_type"),
        ActivityEmailType.check("template_type", name="ck_activity_email_template_type"),
        CheckConstraint(
            f"length(btrim(subject)) > 0 AND length(subject) <= {SUBJECT_MAX} "
            "AND position(chr(10) in subject) = 0 AND position(chr(13) in subject) = 0",
            name="ck_activity_email_template_subject",
        ),
        CheckConstraint(
            f"length(btrim(body)) > 0 AND length(body) <= {BODY_MAX}",
            name="ck_activity_email_template_body",
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    template_type = Column(String(40), nullable=False)
    subject = Column(String(SUBJECT_MAX), nullable=False)
    body = Column(Text, nullable=False)
    updated_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)


class ActivityEmailPreference(TimeStampedModel, VersionedMixin):
    """Si una persona es elegible para cada correo. Apagado por defecto."""

    __tablename__ = "activity_email_preference"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_activity_email_preference_company_user"),
        ForeignKeyConstraint(
            ["user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_activity_email_preference_membership",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    midday_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    end_of_day_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    #: Reportes estratégicos (V1.2): independientes de los motivacionales y,
    #: como ellos, apagados. Sólo se pueden activar para un mando con equipo.
    strategic_midday_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    strategic_end_of_day_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    updated_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)


class DeliveryStatus(BusinessEnum):
    """Estados de un envío real (RTE-MAIL-CP4). `accepted_by_provider` no es
    «entregado»: eso sólo lo sabe la bandeja de destino."""

    PENDING = "pending"
    CLAIMED = "claimed"
    ACCEPTED_BY_PROVIDER = "accepted_by_provider"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"
    SKIPPED = "skipped"
    UNKNOWN_OUTCOME = "unknown_outcome"


class DeliverySource(BusinessEnum):
    SCHEDULE = "schedule"
    RECONCILE = "reconcile"
    MANUAL = "manual"


class ActivityEmailDelivery(TimeStampedModel, VersionedMixin):
    """El registro **productivo** de envíos de correos de actividad.

    Uno solo para el programador interno, el cron de DigitalOcean y el botón
    «Send now» (RTE-MAIL-CP4-01/02): la clave única `(company, recipient, type,
    operational_date)` hace que el mismo correo del mismo día no salga dos veces
    aunque lo pidan a la vez. **No** es `mail_test_send`, que sólo registra
    pruebas con datos ficticios.

    Sólo metadatos: ni asunto, ni cuerpo, ni notas, ni texto del proveedor.
    """

    __tablename__ = "activity_email_delivery"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "recipient_user_id", "report_type", "operational_date",
            name="uq_activity_email_delivery_key",
        ),
        ForeignKeyConstraint(
            ["recipient_user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_activity_email_delivery_membership",
            ondelete="CASCADE",
        ),
        ActivityEmailType.check("report_type", name="ck_activity_email_delivery_type"),
        DeliveryStatus.check("status", name="ck_activity_email_delivery_status"),
        DeliverySource.check("source", name="ck_activity_email_delivery_source"),
        CheckConstraint("attempt_count >= 0", name="ck_activity_email_delivery_attempts"),
        Index("ix_activity_email_delivery_status_due", "status", "due_at"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    recipient_user_id = Column(Integer, nullable=False, index=True)
    report_type = Column(String(40), nullable=False)
    operational_date = Column(Date, nullable=False)
    #: Fin de la ventana de datos del reporte (12:00 local, cierre…).
    cutoff_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, server_default="pending")
    source = Column(String(20), nullable=False)
    attempt_count = Column(Integer, nullable=False, server_default=text("0"))
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    #: Hasta cuándo es de quien la reservó. Una reserva caducada es un
    #: resultado incierto, no una invitación a reenviar.
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    provider_backend = Column(String(40), nullable=True)
    #: Código fijo del motivo (`no_activity`, `token_refused`…), sin texto libre.
    reason_code = Column(String(60), nullable=True)
    requested_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    request_reason = Column(String(300), nullable=True)
    template_version = Column(Integer, nullable=True)
    #: Zona IANA con que se calcularon el corte y el vencimiento.
    time_zone = Column(String(64), nullable=True)


class ActivityEmailResend(TimeStampedModel):
    """Cada **reenvío** de un correo que ya salió (o cuyo resultado es incierto).

    La entrega original sigue siendo una sola fila por persona, tipo y día
    (`activity_email_delivery`); los reenvíos cuelgan de ella, numerados. La
    clave única `(delivery_id, sequence)` hace que un doble clic no mande dos:
    quien pide el reenvío dice cuántos ha visto y sólo uno puede ocupar el
    número siguiente.

    Sólo metadatos, como la entrega: ni asunto, ni cuerpo, ni notas.
    """

    __tablename__ = "activity_email_resend"
    __table_args__ = (
        UniqueConstraint("delivery_id", "sequence", name="uq_activity_email_resend_sequence"),
        DeliveryStatus.check("status", name="ck_activity_email_resend_status"),
        CheckConstraint("sequence >= 1", name="ck_activity_email_resend_sequence"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    delivery_id = Column(
        Integer, ForeignKey("activity_email_delivery.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False)
    provider_backend = Column(String(40), nullable=True)
    reason_code = Column(String(60), nullable=True)
    requested_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    request_reason = Column(String(300), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)


class DispatchOutcome(BusinessEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ActivityEmailDispatchRun(Base):
    """La **última** pasada de cada reloj del envío automático (RTE-MAIL-CLOSE-01).

    Una fila por origen (`schedule`, el programador interno; `reconcile`, el
    Scheduled Job de DigitalOcean), sobrescrita en cada pasada: es un latido,
    no un historial. Lo que la pantalla necesita para decir «el job corrió hace
    3 min» o «no se ha visto nunca» sin leer logs. Sin datos de personas: sólo
    contadores.
    """

    __tablename__ = "activity_email_dispatch_run"
    __table_args__ = (
        CheckConstraint("source IN ('schedule', 'reconcile')", name="ck_activity_email_dispatch_run_source"),
        DispatchOutcome.check("outcome", name="ck_activity_email_dispatch_run_outcome"),
    )

    source = Column(String(20), primary_key=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=False)
    outcome = Column(String(20), nullable=False)
    enabled = Column(Boolean, nullable=False)
    dry_run = Column(Boolean, nullable=False)
    counts = Column(JSONB, nullable=False)
