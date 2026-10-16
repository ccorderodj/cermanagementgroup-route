from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class AuditEvent(Base):
    """Registro append-only de lo que cambió, quién y cuándo.

    Una sola tabla para todos los dominios. La alternativa —una tabla de
    historia por cada entidad— multiplica el esquema por dos y obliga a repetir
    la misma lógica en cada módulo; cada dominio nuevo sería otra oportunidad
    de escribirla mal.

    Qué NO es
    ---------
    No es la evidencia inmutable de un dominio (historiales firmados, revisiones
    aprobadas). Aquellas son **registros de negocio** con su propio ciclo de vida y sus
    propias pantallas; esto es la traza técnica de las mutaciones. Se parecen,
    pero mezclarlas obligaría a que una corrección de evidencia y un cambio de
    teléfono compartieran tabla y permisos.

    Append-only de verdad
    ---------------------
    No hay endpoint de actualización ni de borrado, y además un disparador de
    la base rechaza `UPDATE` y `DELETE` sobre la tabla (ver la migración). Sin
    el disparador, "append-only" es una promesa que se rompe la primera vez que
    alguien abre una consola de SQL.

    `changes` guarda `{"campo": {"old": ..., "new": ...}}` como JSONB. Es uno de
    los usos que la especificación admite explícitamente: el contenido es un
    diff variable, no un modelo de dominio.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        # El acceso normal es "la historia de esta ficha, lo más reciente
        # primero". Sin el índice compuesto, cada consulta recorre la tabla
        # entera, que es la que más crece de todo el esquema.
        Index(
            "ix_audit_event_entity",
            "company_id",
            "entity_type",
            "entity_id",
            "id",
        ),
        # Cruzar un evento con el log del servidor por su `X-Request-ID`.
        Index("ix_audit_event_request", "request_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)

    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type = Column(String(60), nullable=False)
    entity_id = Column(BigInteger, nullable=False)
    action = Column(String(40), nullable=False)

    # `SET NULL` y no `CASCADE`: borrar a una persona no puede borrar la traza
    # de lo que hizo. El evento sobrevive sin actor antes que desaparecer.
    actor_user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    summary = Column(String(500), nullable=True)
    changes = Column(JSONB, nullable=True)

    # Contexto de la petición (fase 12, WP-9; docs 03 y 08). Nulos en los eventos
    # anteriores y en los que no nacen de una petición —un job del planificador—.
    #: El `X-Request-ID` de la petición: cruza el evento con el log.
    request_id = Column(String(64), nullable=True)
    #: El rol del actor en esta compañía cuando actuó. Se congela: si mañana le
    #: cambian el rol, el evento sigue diciendo con qué rol lo hizo.
    actor_role = Column(String(60), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(300), nullable=True)
    #: El motivo que declaró quien actuó, cuando la acción lo pide.
    reason = Column(String(500), nullable=True)

    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} {self.entity_type}#{self.entity_id} "
            f"{self.action}>"
        )
