"""
Vehículos de CER Route y su asignación a supervisores.

Tres modelos y una regla que los ata: **el vehículo actual de un supervisor no
se guarda en ninguna parte**. Se deriva de `vehicle_assignment`, que es quien
posee esa verdad. Guardar además una copia en el perfil crearía dos respuestas
para la misma pregunta, y la segunda empezaría a mentir en cuanto alguien
cambiara de vehículo sin actualizarla (invariante 9 de `AGENTS.md`).

El aislamiento por tenant no se confía a ningún servicio: las referencias entre
estas tablas son **claves foráneas compuestas** `(id, company_id)`, así que
PostgreSQL rechaza asignar el vehículo de otra compañía aunque el código se
olvide de comprobarlo. Es el mismo patrón que `fk_user_company_role_same_company`.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from app.core.enums import BusinessEnum
from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin


class FuelGrade(BusinessEnum):
    """Grados de combustible admitidos por el modelo certificado en RTE01.

    Valores estables, no etiquetas: la interfaz traduce `midgrade` a
    "Midgrade". Guardar la etiqueta convertiría un cambio de texto de pantalla
    en una migración de datos.
    """

    REGULAR = "regular"
    MIDGRADE = "midgrade"
    PREMIUM = "premium"
    DIESEL = "diesel"


class Vehicle(TimeStampedModel, IsActiveMixin, VersionedMixin):
    """Vehículo de la compañía, con los datos operativos que RTE01 fijó.

    Es **configuración operativa, no gestión de flota**: no hay mantenimiento,
    ni VIN, ni seguros, ni telemetría. Lo que hay es lo que el cálculo de
    combustible necesitará más adelante (`operational_mpg`, `fuel_grade`) y lo
    que identifica la unidad para quien la administra.

    No se borra: se desactiva. Un vehículo con jornadas históricas detrás no
    puede desaparecer sin llevarse por delante la trazabilidad de esas jornadas,
    así que `is_active` es el final de su ciclo de vida.
    """

    __tablename__ = "vehicle"
    __table_args__ = (
        FuelGrade.check("fuel_grade", name="ck_vehicle_fuel_grade"),
        # Diana de las FK compuestas: lo que hace imposible referenciar un
        # vehículo de otro tenant.
        UniqueConstraint("id", "company_id", name="uq_vehicle_id_company"),
        # La unidad es como la compañía llama a ese vehículo por dentro. Dos
        # unidades iguales en el mismo tenant harían ambigua cualquier
        # conversación sobre "la V-014".
        UniqueConstraint("company_id", "unit", name="uq_vehicle_company_unit"),
        CheckConstraint("operational_mpg > 0", name="ck_vehicle_operational_mpg_positive"),
        CheckConstraint(
            "year >= 1900 AND year <= 2100", name="ck_vehicle_year_range"
        ),
        Index("ix_vehicle_company_active", "company_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    make = Column(String(60), nullable=False)
    model = Column(String(60), nullable=False)
    year = Column(Integer, nullable=False)
    #: Identificador interno de la unidad ("V-014").
    unit = Column(String(40), nullable=False)

    fuel_grade = Column(String(20), nullable=False)
    #: Millas por galón **operativas**: una entrada de la estimación, no una
    #: especificación del fabricante. `Numeric` y no `Float` porque acaba en un
    #: cálculo de coste y el binario de coma flotante no es lo que se quiere ahí.
    operational_mpg = Column(Numeric(5, 2), nullable=False)

    def __repr__(self) -> str:
        return f"<Vehicle id={self.id} unit={self.unit} company_id={self.company_id}>"


class SupervisorProfile(TimeStampedModel, IsActiveMixin, VersionedMixin):
    """Extensión de dominio de un usuario que hace trabajo de campo en Route.

    **No es una segunda ficha de persona.** El nombre, el correo, la
    autenticación y la pertenencia al tenant siguen siendo de `user` y
    `user_company`; aquí no se copia ninguno. Lo que esta tabla añade es una
    sola cosa: que *esta* identidad, en *esta* compañía, es un supervisor de
    Route al que se le puede asignar un vehículo.

    Por qué está casi vacía
    -----------------------
    Porque en RTE02 no hay ningún atributo de campo que exista de verdad. El
    vehículo actual se deriva de `vehicle_assignment` (§6.1 de las
    instrucciones), y se decidió no inventar columnas para poblarla: una tabla
    con campos que nadie escribe es peor que una tabla pequeña, porque parece
    que el dato existe. Es el punto de extensión donde entrarán los atributos
    de campo cuando los haya.

    La FK compuesta `(user_id, company_id) -> user_company` es lo que impide
    crear un perfil para alguien que no pertenece a la compañía, sin depender
    de que ningún servicio se acuerde de comprobarlo.
    """

    __tablename__ = "supervisor_profile"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "user_id", name="uq_supervisor_profile_company_user"
        ),
        UniqueConstraint("id", "company_id", name="uq_supervisor_profile_id_company"),
        ForeignKeyConstraint(
            ["user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_supervisor_profile_membership",
            ondelete="CASCADE",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<SupervisorProfile id={self.id} user_id={self.user_id} "
            f"company_id={self.company_id}>"
        )


class VehicleAssignment(TimeStampedModel):
    """Qué vehículo condujo un supervisor, y desde cuándo hasta cuándo.

    Historia con fechas de vigencia, no un campo que se sobrescribe. Cambiar de
    vehículo **cierra** la asignación anterior (`effective_to`) e inserta una
    nueva; la fila antigua se queda para que una jornada de marzo siga sabiendo
    con qué vehículo se hizo.

    La regla que la base garantiza
    ------------------------------
    `uq_vehicle_assignment_current` es un índice único **parcial**
    (`WHERE effective_to IS NULL`): un supervisor no puede tener dos
    asignaciones vigentes a la vez. Dos peticiones simultáneas que intenten
    asignarle vehículo no producen dos filas actuales — la segunda choca contra
    el índice. Comprobarlo en Python sólo funciona mientras nadie se olvide y
    mientras no haya concurrencia real; comprobarlo en la base funciona siempre
    (invariante 6).

    Lo que **no** se restringe: que un vehículo lo conduzcan varios supervisores.
    CER no aprobó esa exclusividad, así que no se inventa aquí.

    Por qué no es append-only
    -------------------------
    Cerrar una asignación es escribir su `effective_to`, y un disparador
    append-only lo impediría. La inmutabilidad que importa —que la historia no
    se reescriba— se consigue no borrando filas y dejando traza de cada cambio
    en `audit_event`.
    """

    __tablename__ = "vehicle_assignment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["supervisor_profile_id", "company_id"],
            ["supervisor_profile.id", "supervisor_profile.company_id"],
            name="fk_vehicle_assignment_supervisor_same_company",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["vehicle_id", "company_id"],
            ["vehicle.id", "vehicle.company_id"],
            name="fk_vehicle_assignment_vehicle_same_company",
            ondelete="RESTRICT",
        ),
        # Una sola asignación vigente por supervisor. Parcial a propósito: las
        # cerradas pueden repetirse cuantas veces haga falta.
        Index(
            "uq_vehicle_assignment_current",
            "company_id",
            "supervisor_profile_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_vehicle_assignment_period",
        ),
        Index(
            "ix_vehicle_assignment_history",
            "company_id",
            "supervisor_profile_id",
            "effective_from",
        ),
        Index("ix_vehicle_assignment_vehicle", "company_id", "vehicle_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supervisor_profile_id = Column(Integer, nullable=False)
    vehicle_id = Column(Integer, nullable=False)

    effective_from = Column(DateTime(timezone=True), nullable=False)
    #: `NULL` significa **vigente**. Es lo que el índice parcial usa para contar
    #: cuántas asignaciones actuales tiene un supervisor.
    effective_to = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<VehicleAssignment id={self.id} supervisor={self.supervisor_profile_id} "
            f"vehicle={self.vehicle_id} from={self.effective_from} to={self.effective_to}>"
        )
