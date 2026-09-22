from sqlalchemy import Column, Integer, String, Text

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel


class Permission(TimeStampedModel, IsActiveMixin):
    """Una capacidad del sistema. Catalogo GLOBAL, definido por el codigo.

    `users.read` significa lo mismo en todos los tenants, asi que no tiene
    sentido una copia por compania: multiplicaria las filas sin anadir ninguna
    distincion real. Lo que si es del tenant es el rol que agrupa capacidades,
    y por eso `role` si lleva `company_id`.

    El catalogo lo define `app/core/rbac/catalog.py` y lo siembra el bootstrap.
    No hay endpoints para crear ni borrar permisos: un administrador de tenant
    no inventa capacidades, porque una capacidad sin codigo detras no hace nada.
    """

    __tablename__ = "permission"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name}>"
