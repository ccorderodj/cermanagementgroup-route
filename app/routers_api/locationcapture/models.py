"""
Captura periódica de ubicación (RTE-LOC-02): configuración y muestras.

Independiente, opcional y reversible
------------------------------------
No es un motor de ubicación nuevo ni toca el de eventos: `location_fix` sigue
siendo el punto de cada evento del ciclo de vida, append-only, y es el único
que leen el millaje oficial y el visor de ruta. Las muestras periódicas viven
en su propia tabla y **ningún consumidor de routing o millaje las lee**.

* `LocationCaptureSetting`: por compañía, apagada por defecto, intervalo de
  300 s. La edita quien tenga `route.locationcapture.manage` (a demanda).
* `LocationSample`: un punto cada N segundos mientras la jornada está activa y
  la web puede pedir la ubicación. Sin garantía con la pantalla bloqueada.

Por qué `location_sample` no está particionada (todavía)
--------------------------------------------------------
Una tabla particionada en PostgreSQL sólo admite claves únicas que incluyan la
columna de partición. La idempotencia que pide la instrucción es
`(company_id, client_sample_id)` sin la hora: particionar por
`server_received_at` la rompería. Se deja como tabla normal con el índice
`(company_id, server_received_at)` que el archivo mensual (RTE-LOC-03) necesita
para cortar por tenant y mes; convertirla en particionada es una decisión de
RTE-LOC-03 con su propio diseño de idempotencia.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin
from app.database import Base

INTERVALO_POR_DEFECTO = 300
INTERVALO_MINIMO = 60
INTERVALO_MAXIMO = 3600


class LocationCaptureSetting(TimeStampedModel, VersionedMixin):
    """La configuración de la captura periódica de **una** compañía.

    Sin fila, la compañía la tiene apagada con 300 s: no se siembra nada.
    """

    __tablename__ = "location_capture_setting"
    __table_args__ = (
        CheckConstraint(
            f"interval_seconds BETWEEN {INTERVALO_MINIMO} AND {INTERVALO_MAXIMO}",
            name="ck_location_capture_setting_interval",
        ),
    )

    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), primary_key=True)
    enabled = Column(Boolean, nullable=False, server_default=text("false"))
    interval_seconds = Column(Integer, nullable=False, server_default=text(str(INTERVALO_POR_DEFECTO)))
    updated_by_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)


class LocationSample(Base):
    """Una muestra periódica. Los datos del dispositivo, tal como se midieron."""

    __tablename__ = "location_sample"
    __table_args__ = (
        UniqueConstraint("company_id", "client_sample_id", name="uq_location_sample_client_id"),
        ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_location_sample_session_same_company",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
            name="ck_location_sample_coordinates",
        ),
        CheckConstraint("accuracy_m >= 0", name="ck_location_sample_accuracy"),
        CheckConstraint(
            f"interval_seconds_applied BETWEEN {INTERVALO_MINIMO} AND {INTERVALO_MAXIMO}",
            name="ck_location_sample_interval",
        ),
        Index("ix_location_sample_company_received", "company_id", "server_received_at"),
        Index("ix_location_sample_session", "company_id", "work_session_id", "device_captured_at"),
    )

    id = Column(BigInteger, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    work_session_id = Column(Integer, nullable=False)
    #: Del servidor (la jornada del usuario autenticado), nunca del cuerpo.
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    #: Generado en el dispositivo: reenviar no duplica.
    client_sample_id = Column(UUID(as_uuid=True), nullable=False)
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    accuracy_m = Column(Numeric(10, 2), nullable=False)
    device_captured_at = Column(DateTime(timezone=True), nullable=False)
    server_received_at = Column(DateTime(timezone=True), nullable=False)
    #: El intervalo de la compañía al recibirla.
    interval_seconds_applied = Column(Integer, nullable=False)
