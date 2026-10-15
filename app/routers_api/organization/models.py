"""
La estructura organizacional de CER Route: cargo y superior de cada persona.

Qué es y qué no es
------------------
El **cargo** (CEO, COO, Regional Manager, OSM, Supervisor) organiza: dice quién
depende de quién. **No concede capacidades**: lo que alguien puede hacer sale de
su rol (`route_manager`, `supervisor`, `route_admin`), y sobre qué datos lo hace
sale de esta estructura. Un cargo sin rol con capacidad no ve nada; un rol con
capacidad sin cargo de mando no ve a nadie (`organization.scope`).

Una fila por **periodo**: cambiar de cargo o de superior cierra la vigente y
abre otra. La historia queda, y con ella se decide qué jornadas pasadas ve cada
superior (D-3: por periodo de relación, en el instante `started_at` de cada
jornada).

Lo que garantiza la base, y por qué ahí
---------------------------------------
* **Una asignación abierta por persona y compañía** (índice único parcial).
* **Un único CEO vigente por compañía** (índice único parcial, V1.4).
* **Sin solapes** de vigencia para la misma persona (`EXCLUDE`, como
  `vehicle_assignment`).
* **Periodos no vacíos**: `valid_to > valid_from`.
* **Nadie es su propio superior.**
* **Persona y superior pertenecen a esta compañía**: claves foráneas compuestas
  a `user_company`, así que un superior de otro tenant no se puede escribir.

El nivel estrictamente superior y la ausencia de ciclos dependen de **otras**
filas y los valida el servicio dentro de una transacción con candado por
compañía (`organization.service`).
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint

from app.core.enums import BusinessEnum
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin


class OrgPosition(BusinessEnum):
    """Los cargos aprobados. El nivel está en `NIVEL`, no en el orden del enum."""

    CEO = "ceo"
    COO = "coo"
    REGIONAL_MANAGER = "regional_manager"
    OSM = "osm"
    SUPERVISOR = "supervisor"
    #: V1.3: ejecuta su jornada como el Supervisor y depende **directamente** de
    #: un CEO; fuera del alcance de COO y RM.
    SALES = "sales"


#: El nivel de cada cargo. **OSM y Supervisor comparten nivel**: ninguno manda
#: sobre el otro y no puede haber vínculo entre ellos (decisión del PO).
NIVEL: dict[str, int] = {
    OrgPosition.CEO: 4,
    OrgPosition.COO: 3,
    OrgPosition.REGIONAL_MANAGER: 2,
    OrgPosition.OSM: 1,
    OrgPosition.SUPERVISOR: 1,
    OrgPosition.SALES: 1,
}

#: De qué cargos puede depender cada uno (V1.3, §4). Es la regla
#: **estructural**: dice qué tipo de persona puede ser superior; no transfiere
#: permisos. El superior concreto es `superior_user_id`. El CEO es raíz.
#: Los niveles intermedios son opcionales: un RM puede depender del CEO sin
#: COO, y un OSM o Supervisor del COO o del CEO sin RM. Sales, **sólo** del CEO.
PADRES_PERMITIDOS: dict[str, frozenset[str]] = {
    OrgPosition.CEO: frozenset(),
    OrgPosition.COO: frozenset({OrgPosition.CEO}),
    OrgPosition.REGIONAL_MANAGER: frozenset({OrgPosition.COO, OrgPosition.CEO}),
    OrgPosition.OSM: frozenset(
        {OrgPosition.REGIONAL_MANAGER, OrgPosition.COO, OrgPosition.CEO}
    ),
    OrgPosition.SUPERVISOR: frozenset(
        {OrgPosition.REGIONAL_MANAGER, OrgPosition.COO, OrgPosition.CEO}
    ),
    OrgPosition.SALES: frozenset({OrgPosition.CEO}),
}

#: El cargo de cada rol de Route (V1.3): el cargo **sale del rol**, así que no
#: hay dos controles que puedan contradecirse. `route_manager` (legado) no
#: tiene uno fijo: conserva el que tenía.
CARGO_DE_ROL: dict[str, str] = {
    "CEO": OrgPosition.CEO,
    "COO": OrgPosition.COO,
    "Regional Manager": OrgPosition.REGIONAL_MANAGER,
    "OSM": OrgPosition.OSM,
    "supervisor": OrgPosition.SUPERVISOR,
    "Sales": OrgPosition.SALES,
}

#: Y al revés: qué rol lleva cada cargo.
ROL_DE_CARGO: dict[str, str] = {cargo: rol for rol, cargo in CARGO_DE_ROL.items()}

#: Etiquetas de pantalla.
ETIQUETA: dict[str, str] = {
    OrgPosition.CEO: "CEO",
    OrgPosition.COO: "COO",
    OrgPosition.REGIONAL_MANAGER: "Regional Manager",
    OrgPosition.OSM: "OSM",
    OrgPosition.SUPERVISOR: "Supervisor",
    OrgPosition.SALES: "Sales",
}


class OrgAssignment(TimeStampedModel, VersionedMixin):
    """El cargo y el superior de una persona en una compañía, durante un periodo
    `[valid_from, valid_to)`. `valid_to` nulo: vigente."""

    __tablename__ = "org_assignment"
    __table_args__ = (
        OrgPosition.check("position", name="ck_org_assignment_position"),
        CheckConstraint(
            "superior_user_id IS NULL OR superior_user_id <> user_id",
            name="ck_org_assignment_not_self",
        ),
        CheckConstraint(
            "replaces_user_id IS NULL OR replaces_user_id <> user_id",
            name="ck_org_assignment_replaces_not_self",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_org_assignment_period",
        ),
        ForeignKeyConstraint(
            ["user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_org_assignment_member",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["superior_user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_org_assignment_superior_member",
            ondelete="RESTRICT",
        ),
        ExcludeConstraint(
            ("company_id", "="),
            ("user_id", "="),
            (literal_column("tstzrange(valid_from, valid_to, '[)')"), "&&"),
            name="ex_org_assignment_no_overlap",
            using="gist",
        ),
        Index(
            "uq_org_assignment_current",
            "company_id",
            "user_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        # V1.4: un único CEO vigente por compañía (0019).
        Index(
            "uq_org_assignment_one_ceo",
            "company_id",
            unique=True,
            postgresql_where=text("position = 'ceo' AND valid_to IS NULL"),
        ),
        Index(
            "ix_org_assignment_superior_current",
            "company_id",
            "superior_user_id",
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    position = Column(String(30), nullable=False)
    #: Nulo: raíz de su rama (p. ej. el CEO, o un RM sin COO ni CEO cargados).
    superior_user_id = Column(Integer, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    #: Quién la abrió. La traza completa está en `audit_event`.
    created_by = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    #: V1.5: en la fila que abre «Replace manager», a quién sustituye esta
    #: persona. Con él, el sucesor hereda lo que veía su antecesor.
    replaces_user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="SET NULL", name="fk_org_assignment_replaces_user"),
        nullable=True,
    )
