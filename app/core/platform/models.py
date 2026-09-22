"""
Tablas de plataforma: salud, configuración, secretos, políticas y su traza.

**Nada de esto tiene `company_id`.** Todo lo que vive aquí es del despliegue, no
de una compañía: el servidor de correo, el almacén de evidencia, el escáner. Se
comprobó una por una. Añadir `company_id` obligaría a inventar a qué compañía
pertenece el estado de PostgreSQL, y la respuesta honesta es «a ninguna: a
todas».

Por la misma razón la traza no va a `audit_event`: aquella tabla tiene
`company_id NOT NULL` porque es la historia **de un tenant**, y elegirle una
compañía a un cambio de credenciales del despliegue metería un hecho de
plataforma en la historia de un cliente.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func, text

from app.database import Base


class PlatformHealthCheck(Base):
    """Lo último que se supo de una capacidad diagnosticable.

    Una fila por capacidad, y se pisa: es el estado actual que la pantalla pinta.
    El historial vive en `platform_health_check_run`. `last_success_at` separado
    de `last_checked_at` es lo que permite decir «lleva tres días caído» en vez
    de sólo «ahora falla».
    """

    __tablename__ = "platform_health_check"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(capability_key)) > 0",
            name="ck_platform_health_key_present",
        ),
    )

    id = Column(Integer, primary_key=True)
    capability_key = Column(String(100), nullable=False, unique=True)
    last_status = Column(String(30), nullable=False)
    last_detail = Column(Text, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=False)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_by_user_id = Column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformHealthCheckRun(Base):
    """Cada comprobación, una fila. **Append-only** por disparador.

    Lo pide la pregunta de un operador: no «¿contesta ahora?», sino «¿cuándo
    empezó a fallar y quién lo miró?». La fila de estado se pisa; ésta no.
    """

    __tablename__ = "platform_health_check_run"
    __table_args__ = (
        Index("ix_platform_health_check_run_key", "capability_key", "id"),
        CheckConstraint(
            "trigger IN ('manual', 'scheduled', 'verify')",
            name="ck_platform_health_check_run_trigger",
        ),
    )

    id = Column(BigInteger, primary_key=True)
    capability_key = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False)
    detail = Column(Text, nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    duration_ms = Column(Integer, nullable=True)
    #: `NULL` cuando la lanzó el planificador y no una persona.
    actor_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    trigger = Column(String(20), nullable=False, server_default=text("'manual'"))


class PlatformIntegration(Base):
    """Una integración de terceros: qué proveedor, con qué configuración.

    `config` guarda **sólo lo que no es secreto** —host, bucket, identificadores
    públicos—, validado contra la definición del proveedor
    (`app/core/platform/providers.py`). Los secretos van a `platform_secret`,
    cifrados y relacionados con esta fila.

    `verified_at` se borra en cuanto cambia algo: una verificación demuestra que
    funcionaba **esa** configuración, no la siguiente.
    """

    __tablename__ = "platform_integration"
    __table_args__ = (
        CheckConstraint("length(btrim(key)) > 0", name="ck_platform_integration_key_present"),
    )

    id = Column(Integer, primary_key=True)
    key = Column(String(60), nullable=False, unique=True)
    provider = Column(String(40), nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, nullable=False, server_default=text("1"))
    updated_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformSecret(Base):
    """Una credencial cifrada, colgada de su integración.

    `ON DELETE RESTRICT`: una integración no se borra dejando secretos huérfanos;
    se retiran sus secretos primero, y esa retirada queda en la traza.

    `key_id` es la huella de la llave con la que se cifró —no la llave—, para que
    una rotación sepa qué filas le quedan. `expires_at` existe porque algunas
    credenciales caducan (el client secret de Microsoft 365) y el planificador
    avisa antes de que el correo deje de salir.
    """

    __tablename__ = "platform_secret"
    __table_args__ = (
        UniqueConstraint("integration_id", "name", name="uq_platform_secret_slot"),
        CheckConstraint("octet_length(nonce) = 12", name="ck_platform_secret_nonce_12"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_platform_secret_name_present"),
    )

    id = Column(Integer, primary_key=True)
    integration_id = Column(
        Integer, ForeignKey("platform_integration.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String(60), nullable=False)
    ciphertext = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    key_id = Column(String(16), nullable=False)
    set_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    set_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class PlatformPolicy(Base):
    """Una política operativa editable: subida de archivos, sesión, retención.

    No son secretos, así que no necesitan cifrado ni esperan a ningún almacén:
    antes vivían en el entorno y cambiarlas exigía redesplegar. El valor se
    valida contra su esquema (`app/core/platform/policies.py`).
    """

    __tablename__ = "platform_policy"
    __table_args__ = (
        CheckConstraint("length(btrim(key)) > 0", name="ck_platform_policy_key_present"),
    )

    id = Column(Integer, primary_key=True)
    key = Column(String(60), nullable=False, unique=True)
    value = Column(JSONB, nullable=False)
    version = Column(Integer, nullable=False, server_default=text("1"))
    updated_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformAuditEvent(Base):
    """La traza de plataforma. **Append-only** por disparador.

    Registra quién cambió qué en la configuración del despliegue, con el rol, la
    petición, la IP y el agente. Un secreto aparece como `"changed"`, nunca con
    su valor: la traza la lee más gente que la que puede ver credenciales.
    """

    __tablename__ = "platform_audit_event"
    __table_args__ = (
        Index("ix_platform_audit_event_target", "target", "id"),
    )

    id = Column(BigInteger, primary_key=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    actor_role = Column(String(40), nullable=True)
    action = Column(String(60), nullable=False)
    target = Column(String(100), nullable=False)
    changes = Column(JSONB, nullable=True)
    request_id = Column(String(64), nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(300), nullable=True)
