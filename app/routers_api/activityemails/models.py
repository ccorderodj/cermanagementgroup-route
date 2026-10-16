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
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

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
