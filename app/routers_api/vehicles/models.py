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
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint

from app.core.enums import BusinessEnum
from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.SoftDelete import SoftDeleteMixin
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


class Vehicle(TimeStampedModel, IsActiveMixin, SoftDeleteMixin, VersionedMixin):
    """Vehículo de la compañía, con los datos operativos que RTE01 fijó.

    Es **configuración operativa, no gestión de flota**: no hay mantenimiento,
    ni VIN, ni seguros, ni telemetría. Lo que hay es lo que el cálculo de
    combustible necesitará más adelante (`operational_mpg`, `fuel_grade`) y lo
    que identifica la unidad para quien la administra.

    Desactivar y borrar son distintos (RTE02-A01)
    ----------------------------------------------
    `is_active = False` lo retira del uso operativo pero lo deja en la
    administración, reactivable. `deleted_at` lo saca de la experiencia normal
    del administrador. **La fila no desaparece en ninguno de los dos casos**: un
    vehículo con jornadas históricas detrás no puede irse sin llevarse la
    trazabilidad de esas jornadas — y la base ya lo impide, porque
    `work_session.vehicle_id` y `vehicle_assignment.vehicle_id` lo referencian
    con `RESTRICT`. Ver `app/core/models/SoftDelete.py`.

    Borrar exige además que **no haya una asignación vigente**. Esa regla la
    comprueba el servidor, no la interfaz: ocultar el botón es experiencia de
    usuario, no un control (invariante 8).
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
        #
        # Parcial desde RTE02-A01: una unidad borrada deja de ocupar sitio. Si
        # no, borrar "V-014" impediría dar de alta otro "V-014" para siempre,
        # chocando contra una fila que para el administrador ya no existe.
        Index(
            "uq_vehicle_company_unit",
            "company_id",
            "unit",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
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


class SupervisorProfile(TimeStampedModel, IsActiveMixin, SoftDeleteMixin, VersionedMixin):
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

    Borrar la designación no borra a la persona (RTE02-A01)
    -------------------------------------------------------
    `deleted_at` retira la designación de Route de la experiencia normal del
    administrador. El `user` y su `user_company` **no se tocan**: son del
    núcleo, y quien dejó de ser supervisor sigue siendo un usuario del tenant.

    La fila se marca en vez de destruirse porque `vehicle_assignment` la
    referencia con `CASCADE`: un `DELETE` físico se llevaría por delante todo el
    historial de asignaciones de esa persona, que es justo lo que el addendum
    exige preservar.
    """

    __tablename__ = "supervisor_profile"
    __table_args__ = (
        # Parcial desde RTE02-A01: borrada la designación, la misma persona
        # puede volver a designarse. Con la restricción completa, un borrado
        # sería irreversible y sin explicación visible.
        Index(
            "uq_supervisor_profile_company_user",
            "company_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
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

    Las reglas que la base garantiza
    -------------------------------
    `ex_vehicle_assignment_no_overlap` es la que importa: **ninguna pareja de
    asignaciones del mismo supervisor puede estar vigente en el mismo instante**.
    Es una restricción `EXCLUDE` sobre `tstzrange(effective_from, effective_to,
    '[)')`, así que cubre cualquier forma de solape y no sólo las que a alguien
    se le ocurriera comprobar.

    El intervalo es semiabierto a propósito: reasignar cierra la anterior en
    `effective_to = desde` y abre la nueva en `effective_from = desde`, y con
    `[)` esos dos intervalos se tocan sin solaparse.

    `uq_vehicle_assignment_current` es un índice único **parcial**
    (`WHERE effective_to IS NULL`) y sigue siendo útil, pero es más estrecho:
    sólo impide dos asignaciones **abiertas**. Antes era la única protección de
    la base y por eso se colaba este caso — una cerrada `[Mar 1, Abr 1)` más una
    nueva abierta desde el Feb 1 solapan y ninguna de las dos tiene
    `effective_to IS NULL`. Lo tapaba una comprobación en Python que ni cubría
    todos los casos ni era atómica; ahora lo garantiza la base (invariante 6).

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
        # Ninguna pareja vigente en el mismo instante, sea abierta o cerrada.
        # La declara la migración 0009 en SQL: `ExcludeConstraint` necesita la
        # extensión `btree_gist`, y el orden —extensión primero, restricción
        # después— sólo se puede garantizar allí.
        ExcludeConstraint(
            ("company_id", "="),
            ("supervisor_profile_id", "="),
            (literal_column("tstzrange(effective_from, effective_to, '[)')"), "&&"),
            name="ex_vehicle_assignment_no_overlap",
            using="gist",
        ),
        # Una sola asignación **abierta** por supervisor. Más estrecha que la
        # anterior y parcial a propósito: las cerradas pueden repetirse.
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
