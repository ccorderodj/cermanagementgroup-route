"""
Registro de los envíos de **prueba** de correo (RTE-MAIL-UNIFIED-01, CP1).

Una fila por intento que pasó las barreras, de cualquier camino de prueba: la
del proveedor (Platform › Integrations & Settings, T0) y las de las plantillas
(Activity Emails, T1-T4). Es el presupuesto **compartido** de pruebas: el
límite se cuenta aquí, no por plantilla ni por pantalla.

No es la auditoría (eso sigue en `audit_event` / `platform_audit_event`, que
son append-only): la fila se reserva antes de mandar, con `outcome = pending`,
y se completa al terminar. No guarda asunto, cuerpo ni texto del proveedor.
"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.core.enums import BusinessEnum
from app.database import Base


class MailTestChannel(BusinessEnum):
    PROVIDER = "provider"
    TEMPLATE = "template"


class MailTestOutcome(BusinessEnum):
    PENDING = "pending"
    ACCEPTED_BY_PROVIDER = "accepted_by_provider"
    NOT_SENT_DEVELOPMENT_BACKEND = "not_sent_development_backend"
    CAPTURED_BY_TEST_BACKEND = "captured_by_test_backend"
    FAILED_AUTH = "failed_auth"
    FAILED_UNREACHABLE = "failed_unreachable"


class MailTestSend(Base):
    __tablename__ = "mail_test_send"
    __table_args__ = (
        MailTestChannel.check("channel", name="ck_mail_test_send_channel"),
        MailTestOutcome.check("outcome", name="ck_mail_test_send_outcome"),
        Index("ix_mail_test_send_actor_time", "actor_user_id", "created_at"),
    )

    id = Column(BigInteger, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    #: `NULL` en la prueba del proveedor: es de plataforma, no de un tenant.
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=True)
    channel = Column(String(20), nullable=False)
    #: La integración (`email`, `email_fallback`) o el tipo de plantilla.
    target = Column(String(60), nullable=False)
    destination = Column(String(254), nullable=False)
    outcome = Column(String(40), nullable=False, server_default="pending")
    #: El `name` del backend que de verdad lo tomó (`smtp_basic`, `console`…).
    backend = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
