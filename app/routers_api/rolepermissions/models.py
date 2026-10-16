from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel


class RolePermission(TimeStampedModel, IsActiveMixin):
    """Concesion de una capacidad a un rol.

    No lleva `company_id` y no debe llevarlo: la compania se deduce sin
    ambiguedad por `role_id -> role.company_id`, y la FK con CASCADE garantiza
    que la fila no puede sobrevivir a su rol. Anadir aqui una copia del
    `company_id` crearia un dato redundante que podria contradecir al del rol,
    que es exactamente el tipo de incoherencia que las restricciones existen
    para impedir.
    """

    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uk_role_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(
        Integer,
        ForeignKey("role.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id = Column(
        Integer,
        ForeignKey("permission.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RolePermission role_id={self.role_id} "
            f"permission_id={self.permission_id}>"
        )
