from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func

from app.database import Base


class TimeStampedModel(Base):
    """`created_at` / `updated_at` para todos los modelos.

    Con **zona horaria** (`timestamptz`) y almacenados en UTC (D10). Antes eran
    `timestamp` naive mientras `Users.last_login` y `Users.date_joined` sí
    llevaban zona: en la misma fila convivían los dos tipos, y comparar uno con
    otro en Python lanza `TypeError`. Hoy no ocurría porque nada los comparaba;
    con vencimientos, auditoría o programación de tareas habría sido cuestión de
    tiempo.

    `server_default=func.now()` deja el valor en manos de PostgreSQL, así que una
    inserción por SQL directo —una migración, un script— también lo obtiene.
    """

    __abstract__ = True

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
