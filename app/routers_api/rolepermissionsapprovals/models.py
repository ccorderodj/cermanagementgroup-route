from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel


class ChangeRequestStatus(StrEnum):
    """Estados de una solicitud de cambio de permisos."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RolePermissionChangeRequest(TimeStampedModel, IsActiveMixin):
    """Un cambio de permisos de un rol, esperando revisión.

    La solicitud guarda el **conjunto final deseado** de permisos, no un delta,
    y `role_permission` no se toca hasta que alguien la aprueba. Eso hace que
    conceder y revocar pasen exactamente por el mismo control: antes, quitar un
    permiso lo borraba al instante sin revisión, que era justo lo contrario de
    lo que un maker-checker debe proteger.

    Guardar el conjunto entero (y no el delta) también permite calcular la
    diferencia contra el estado actual en el momento de revisar, que es cuando
    de verdad importa.

    **`company_id` se almacena explícitamente** aunque sea deducible por
    `role_id`. Aquí la redundancia sí se paga: permite filtrar el listado por
    tenant sin un join extra en la consulta más frecuente de la pantalla, y la
    FK compuesta `(role_id, company_id) -> role(id, company_id)` impide que los
    dos valores se contradigan. Sin este campo, un revisor de la compañía A
    podía aprobar por id una solicitud de la compañía B (AUD-SEC-007).
    """

    __tablename__ = "role_permission_change_request"
    __table_args__ = (
        ForeignKeyConstraint(
            ["role_id", "company_id"],
            ["role.id", "role.company_id"],
            name="fk_change_request_role_same_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_change_request_status",
        ),
        # Una sola solicitud pendiente por rol, garantizado por la base.
        # Antes se comprobaba con un SELECT seguido de un INSERT, así que dos
        # peticiones simultáneas creaban dos pendientes (AUD-BE-029).
        Index(
            "uq_change_request_one_pending_per_role",
            "role_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_change_request_company", "company_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    role_id = Column(Integer, nullable=False, index=True)
    company_id = Column(Integer, nullable=False)

    # `Integer`, igual que `user.id`. Antes eran `BigInteger` contra una PK
    # `Integer`: los tipos no coincidían a ambos lados de la clave foránea.
    requested_by_user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_note = Column(Text, nullable=True)

    status = Column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
        index=True,
    )

    # Conjunto final de permisos que se pide dejar en el rol.
    requested_permission_ids = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    # Se cargan con `joined` porque el listado siempre los muestra: quién pidió
    # el cambio y quién lo revisó son parte de la fila, no un detalle opcional.
    role = relationship(
        "Role",
        lazy="joined",
        primaryjoin="RolePermissionChangeRequest.role_id == Role.id",
        foreign_keys=[role_id],
        viewonly=True,
    )
    requested_by_user = relationship(
        "Users",
        lazy="joined",
        foreign_keys=[requested_by_user_id],
    )
    reviewed_by_user = relationship(
        "Users",
        lazy="joined",
        foreign_keys=[reviewed_by_user_id],
    )

    @property
    def is_pending(self) -> bool:
        return self.status == ChangeRequestStatus.PENDING

    def __repr__(self) -> str:
        return (
            "<RolePermissionChangeRequest "
            f"id={self.id} role_id={self.role_id} status={self.status}>"
        )
