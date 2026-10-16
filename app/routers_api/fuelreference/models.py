"""
La referencia de combustible y la estimación congelada de cada jornada (RTE09).

Qué es, y qué no
----------------
Es el **contrato en base de datos** del precio de combustible. Lo que lo llena
—un trabajo programado, una importación, otra ingesta aprobada— vive fuera:
Reports sólo lee filas que ya existen. Por eso aquí no hay proveedor, ni
`scraper`, ni credenciales, ni pantalla de carga (autorización RTE09, §5–§6).

`fuel_reference` — historia, nunca un precio mutable
-----------------------------------------------------
Una fila por precio observado: compañía, estado, grado, fecha efectiva, precio,
fuente y cuándo se cargó. **Sólo se añaden filas** (disparador append-only): un
precio nuevo no reescribe el anterior, y una corrección es otra fila. Si llegan
dos para el mismo estado, grado y fecha efectiva, vale la **cargada después**.

El precio es **estrictamente positivo** en la base. Un precio de 0 no describe
ninguna gasolinera; admitirlo dejaría colar el «precio falso de 0» que la
autorización prohíbe insertar para que la multiplicación funcione (§17).

Por compañía, no global: el aislamiento de tenant es explícito en cada fila y
en cada consulta, como en el resto del dominio.

`work_session_fuel_estimate` — el resultado que ya no cambia
------------------------------------------------------------
Cuando una jornada tiene todas sus entradas —millas oficiales finales, MPG,
grado, estado y una referencia aplicable— su estimación se **congela** aquí con
toda su procedencia. Una referencia cargada después no la reescribe (§9).

Lo que **no** se guarda nunca es un cero por falta de precio: mientras no hay
referencia, la estimación se calcula al vuelo y no deja fila, así que cuando el
precio llegue la jornada se resuelve con él (§8).
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.database import Base
from app.routers_api.vehicles.models import FuelGrade


class FuelReference(Base):
    __tablename__ = "fuel_reference"
    __table_args__ = (
        FuelGrade.check("fuel_grade", name="ck_fuel_reference_fuel_grade"),
        CheckConstraint("state_code ~ '^[A-Z]{2}$'", name="ck_fuel_reference_state_code"),
        CheckConstraint("price_per_gallon > 0", name="ck_fuel_reference_price_positive"),
        CheckConstraint("length(trim(source)) > 0", name="ck_fuel_reference_source"),
        # La consulta de resolución: el precio vigente de un estado y un grado a
        # una fecha. `company_id` primero, como en el resto de índices de tenant.
        Index(
            "ix_fuel_reference_lookup",
            "company_id",
            "state_code",
            "fuel_grade",
            "effective_date",
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(
        Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False
    )
    state_code = Column(String(2), nullable=False)
    fuel_grade = Column(String(20), nullable=False)
    #: Dólares por galón, con la precisión que publican las fuentes (4 decimales).
    price_per_gallon = Column(Numeric(8, 4), nullable=False)
    #: El día desde el que este precio aplica. Se compara con `session_date`.
    effective_date = Column(Date, nullable=False)
    #: De dónde viene, en palabras: «AAA Georgia Avg.», «EIA weekly», un fichero.
    source = Column(String(120), nullable=False)
    #: Identificador o enlace de la observación en la fuente, si lo hay.
    source_reference = Column(Text, nullable=True)
    loaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkSessionFuelEstimate(Base):
    __tablename__ = "work_session_fuel_estimate"
    __table_args__ = (
        # Una estimación final por jornada: congelarla dos veces, o dos veces a
        # la vez, no puede dejar dos resultados.
        UniqueConstraint("work_session_id", name="uq_work_session_fuel_estimate_session"),
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_fuel_estimate_session_same_company",
            ondelete="CASCADE",
        ),
        FuelGrade.check("fuel_grade", name="ck_fuel_estimate_fuel_grade"),
        CheckConstraint("operational_mpg > 0", name="ck_fuel_estimate_mpg_positive"),
        CheckConstraint("price_per_gallon > 0", name="ck_fuel_estimate_price_positive"),
        CheckConstraint(
            "official_miles >= 0 AND estimated_gallons >= 0 AND estimated_cost >= 0",
            name="ck_fuel_estimate_non_negative",
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(
        Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False
    )
    work_session_id = Column(Integer, nullable=False)
    #: La referencia aplicada. `RESTRICT`: una referencia usada no desaparece.
    fuel_reference_id = Column(
        Integer, ForeignKey("fuel_reference.id", ondelete="RESTRICT"), nullable=False
    )
    # Las entradas, copiadas: la procedencia se lee aquí sin reconstruir nada.
    state_code = Column(String(2), nullable=False)
    fuel_grade = Column(String(20), nullable=False)
    operational_mpg = Column(Numeric(5, 2), nullable=False)
    official_miles = Column(Numeric(12, 4), nullable=False)
    price_per_gallon = Column(Numeric(8, 4), nullable=False)
    effective_date = Column(Date, nullable=False)
    source = Column(String(120), nullable=False)
    # El resultado.
    estimated_gallons = Column(Numeric(12, 4), nullable=False)
    estimated_cost = Column(Numeric(12, 4), nullable=False)
    calculated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
