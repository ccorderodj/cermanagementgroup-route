"""
Tablas de integración.

Cuatro tablas y ninguna de dominio:

* `webhook_endpoint` — una contraparte que nos envía eventos (`inbound`) o a la
  que se los enviamos (`outbound`). Su secreto HMAC va cifrado con la llave de
  plataforma; nunca en claro y nunca devuelto por la API salvo al crearlo o
  rotarlo.
* `webhook_delivery` — la cola de entregas salientes con su estado y reintentos.
  Es mutable a propósito: es una máquina de estados, no evidencia.
* `integration_event` — **append-only** por disparador: qué entró o salió,
  cuándo, de quién, con qué identificador de correlación y huella del cuerpo.
  No guarda el cuerpo: los metadatos bastan para auditar sin copiar datos de
  dominio a una tabla transversal.
* `idempotency_record` — la respuesta recordada de una clave de idempotencia.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin
from app.database import Base


class WebhookDirection(BusinessEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DeliveryStatus(BusinessEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class IntegrationEventStatus(BusinessEnum):
    #: Firmado, verificado y aceptado por un manejador.
    ACCEPTED = "accepted"
    #: Firmado y verificado, pero ninguna parte de la aplicación lo maneja.
    UNHANDLED = "unhandled"
    #: Ya se había recibido: no se vuelve a procesar.
    DUPLICATE = "duplicate"
    #: Firma, marca de tiempo o endpoint inválidos.
    REJECTED = "rejected"
    #: Encolado para salir.
    QUEUED = "queued"


class WebhookEndpoint(TimeStampedModel, VersionedMixin):
    __tablename__ = "webhook_endpoint"
    __table_args__ = (
        WebhookDirection.check("direction", name="ck_webhook_endpoint_direction"),
        UniqueConstraint("public_id", name="uq_webhook_endpoint_public_id"),
        UniqueConstraint("company_id", "name", name="uq_webhook_endpoint_company_name"),
        Index("ix_webhook_endpoint_company_direction", "company_id", "direction", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    #: Identificador opaco que aparece en la URL entrante. No es el `id`: la URL
    #: se comparte con la contraparte y no debe revelar cuántos endpoints hay.
    public_id = Column(String(40), nullable=False)
    name = Column(String(120), nullable=False)
    direction = Column(String(10), nullable=False)
    #: Aplicación de la contraparte (por ejemplo `cer-staffing`).
    counterpart_app = Column(String(80), nullable=False)
    #: Destino de las entregas salientes. Nulo en los entrantes.
    url = Column(String(500), nullable=True)
    #: Tipos de evento que acepta (entrante) o a los que se suscribe (saliente).
    #: Lista vacía = todos.
    event_types = Column(JSONB, nullable=False, server_default="[]")
    is_active = Column(Boolean, nullable=False, server_default="true")

    secret_ciphertext = Column(LargeBinary, nullable=False)
    secret_nonce = Column(LargeBinary, nullable=False)
    secret_key_id = Column(String(64), nullable=False)
    secret_rotated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WebhookDelivery(TimeStampedModel):
    __tablename__ = "webhook_delivery"
    __table_args__ = (
        DeliveryStatus.check("status", name="ck_webhook_delivery_status"),
        UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_delivery_endpoint_event"),
        Index("ix_webhook_delivery_due", "status", "next_attempt_at"),
    )

    id = Column(BigInteger, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    endpoint_id = Column(
        Integer, ForeignKey("webhook_endpoint.id", ondelete="CASCADE"), nullable=False
    )
    #: Identificador único del evento, igual en todos los reintentos: es lo que
    #: la contraparte usa para no procesarlo dos veces.
    event_id = Column(String(64), nullable=False)
    event_type = Column(String(120), nullable=False)
    payload = Column(JSONB, nullable=False)
    correlation_id = Column(String(64), nullable=True)
    status = Column(String(12), nullable=False, server_default=DeliveryStatus.PENDING.value)
    attempts = Column(SmallInteger, nullable=False, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_status_code = Column(SmallInteger, nullable=True)
    last_error = Column(String(500), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class IntegrationEvent(Base):
    """Metadatos append-only de cada mensaje de integración."""

    __tablename__ = "integration_event"
    __table_args__ = (
        WebhookDirection.check("direction", name="ck_integration_event_direction"),
        IntegrationEventStatus.check("status", name="ck_integration_event_status"),
        Index("ix_integration_event_company_time", "company_id", "occurred_at"),
        Index("ix_integration_event_lookup", "endpoint_id", "event_id"),
        Index("ix_integration_event_correlation", "correlation_id"),
    )

    id = Column(BigInteger, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=True)
    endpoint_id = Column(
        Integer, ForeignKey("webhook_endpoint.id", ondelete="SET NULL"), nullable=True
    )
    direction = Column(String(10), nullable=False)
    counterpart_app = Column(String(80), nullable=True)
    event_id = Column(String(64), nullable=True)
    event_type = Column(String(120), nullable=True)
    status = Column(String(12), nullable=False)
    #: `X-Request-ID` de la petición que lo produjo o recibió.
    request_id = Column(String(64), nullable=True)
    #: Identificador que la cadena entre aplicaciones conserva de punta a punta.
    correlation_id = Column(String(64), nullable=True)
    #: SHA-256 del cuerpo exacto recibido o enviado.
    payload_sha256 = Column(String(64), nullable=True)
    detail = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint("scope", "company_id", "key", name="uq_idempotency_record_scope_key"),
        Index("ix_idempotency_record_expires", "expires_at"),
    )

    id = Column(BigInteger, primary_key=True)
    #: Qué operación protege (por ejemplo `webhooks.inbound`).
    scope = Column(String(120), nullable=False)
    #: 0 para operaciones sin tenant: un UNIQUE con NULL no deduplica.
    company_id = Column(Integer, nullable=False, server_default="0")
    key = Column(String(200), nullable=False)
    #: Huella de la petición: la misma clave con otro cuerpo es un error.
    request_sha256 = Column(String(64), nullable=False)
    response_status = Column(SmallInteger, nullable=False)
    response_body = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
