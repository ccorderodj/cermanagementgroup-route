from sqlalchemy import Column, Integer, String

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel


class Region(TimeStampedModel, IsActiveMixin):
    """Catalogo global de estados de EE.UU.

    No lleva `company_id` a proposito: los estados de EE.UU. son los mismos para
    todos los tenants. Lo que si es del tenant es en cuales opera, y eso vive en
    `company_state`.

    No declara `relationship` hacia `company_state`: la que habia obligaba a
    silenciar un solapamiento con `overlaps=` y cargaba filas de todas las
    companias al leer una region (AUD-DB-023).
    """

    __tablename__ = "region"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(2), unique=True, nullable=False)
    name = Column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<Region id={self.id} code={self.code} name={self.name}>"
