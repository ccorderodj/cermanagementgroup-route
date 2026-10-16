from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel


class RoleCategory(StrEnum):
    """Categoría del rol, que determina la autoridad para aprobar cambios.

    La distinción no es jerárquica por gusto: decide **quién puede revisar** un
    cambio de permisos. Un rol operativo puede solicitarlos, pero solo alguien
    de dirección/gestión —o un administrador de plataforma— puede aprobarlos.
    """

    MANAGEMENT = "management"
    OPERATIVE = "operative"


class Role(TimeStampedModel, IsActiveMixin):
    """Un rol **pertenece a una compañía** (D8).

    Antes `role` era un catálogo global: con dos tenants, editar los permisos
    del rol `admin` desde la compañía A cambiaba lo que podía hacer el `admin`
    de la B, y el listado de roles de A mostraba los de B (AUD-SEC-006).

    Lo que NO se hizo, a propósito: copiar `Permission` por compañía.
    Un permiso es una **capacidad del sistema** —`users.read` significa lo mismo
    en todos los tenants— y su catálogo lo define el código, no los
    administradores. Lo que varía por compañía es qué roles existen y qué
    capacidades agrupa cada uno. Por eso `role` es del tenant y `permission` es
    global.

    `uq_role_id_company` parece redundante con la clave primaria, y lo es como
    restricción de unicidad. Está para otra cosa: es el destino de la clave
    foránea compuesta de `user_company`, que es lo que garantiza a nivel de base
    que un usuario no pueda recibir el rol de otra compañía.
    """

    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_role_company_name"),
        # Destino de la FK compuesta de `user_company` y de
        # `role_permission_change_request`.
        UniqueConstraint("id", "company_id", name="uq_role_id_company"),
        CheckConstraint(
            "category IN ('management', 'operative')",
            name="ck_role_category",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(
        String(20),
        nullable=False,
        server_default=text("'operative'"),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} company_id={self.company_id} name={self.name}>"
