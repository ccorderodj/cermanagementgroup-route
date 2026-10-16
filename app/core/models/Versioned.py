from sqlalchemy import Column, Integer, text

from app.database import Base


class VersionedMixin(Base):
    """Bloqueo optimista para los registros operativos que se editan a mano.

    Dos personas abriendo la misma ficha de cliente y guardando con un minuto de
    diferencia es el caso normal, no el raro: quien guarda segundo pisa lo que
    escribió el primero sin que nadie se entere. Con `version`, la segunda
    escritura llega con un número que ya no es el actual y el servicio responde
    409 en vez de sobrescribir en silencio.

    Se aplica solo donde hay riesgo real de edición concurrente (fichas de
    cliente, configuración operativa). Los catálogos y las tablas de evidencia
    inmutable no lo necesitan: unos no se editan y las otras no se reescriben.

    Ver `app/core/dao/concurrency.py` para la comprobación.
    """

    __abstract__ = True

    version = Column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
