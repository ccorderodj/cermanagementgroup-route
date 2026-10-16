from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.SoftDelete import SoftDeleteMixin
from app.core.models.TimeStamped import TimeStampedModel


class Company(TimeStampedModel, IsActiveMixin):
    """El tenant técnico de la plataforma.

    Ojo con no confundir dos conceptos que se parecen: `Company` es **quién usa
    la plataforma**. Las empresas con las que un tenant trabaja (clientes,
    proveedores) son un dominio de la aplicación que las posee, y no son
    `Company`.

    `subdomain` es la clave de enrutamiento: `CompanyResolverMiddleware` resuelve
    el tenant a partir de `<subdomain>.<BASE_DOMAIN>`. Por eso es obligatorio, y
    por eso su edición está fuera del perfil de la compañía (D5): cambiarlo deja
    al tenant inalcanzable para todos sus usuarios.
    """

    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)

    domain = Column(String(255), nullable=True, unique=True, index=True)
    subdomain = Column(String(255), nullable=False, unique=True, index=True)

    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    phone_secondary = Column(String(20), nullable=True)
    website = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)

    brand_primary_color = Column(String(7), nullable=True)
    brand_secondary_color = Column(String(7), nullable=True)
    pdf_text_color = Column(String(7), nullable=True)
    pdf_muted_text_color = Column(String(7), nullable=True)
    pdf_surface_color = Column(String(7), nullable=True)

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name} subdomain={self.subdomain}>"


class UserCompany(TimeStampedModel, IsActiveMixin, SoftDeleteMixin):
    """Pertenencia de un usuario a una compañía, con su rol en ella.

    Dos invariantes, ambas **garantizadas por la base** y no por código Python:

    1. `uq_user_company_user_company` — un usuario tiene como mucho una
       pertenencia por compañía. Sin ella, dos filas activas hacían que la
       consulta de login devolviera múltiples resultados y respondiera 500
       (AUD-DB-002).

    2. `fk_user_company_role_same_company` — el rol asignado pertenece a la
       **misma** compañía que la pertenencia. Es una FK compuesta
       `(role_id, company_id) -> role(id, company_id)`: PostgreSQL rechaza la
       fila si el rol es de otro tenant, sin depender de que ningún servicio se
       acuerde de comprobarlo.

    Borrar a alguien de un tenant es borrar esta fila, no la persona
    -----------------------------------------------------------------
    La identidad (`user`) puede pertenecer a varias compañías y al plano de
    plataforma; destruirla para sacar a alguien de **un** tenant sería un daño
    desproporcionado y fuera del alcance de quien administra ese tenant. Lo que
    se retira es la pertenencia, que es lo que ese administrador posee.

    Y se retira con lápida, no con `DELETE`: `supervisor_profile` referencia
    esta fila con `CASCADE`, así que destruirla se llevaría por delante la
    designación de Route de esa persona y, tras ella, su historial de
    asignaciones de vehículo.

    **`deleted_at` cierra el acceso.** No es sólo presentación: las dos puertas
    de entrada —`find_active_membership`, que autoriza cada petición, y
    `find_login_candidate`, que autentica— lo exigen `NULL`. Una pertenencia
    borrada no entra, igual que una desactivada.

    Límite conocido y deliberado
    ----------------------------
    `uq_user_company_user_company` **no** se hizo parcial. Eso significa que
    borrar es terminal bajo el modelo actual: esa persona no puede volver a
    darse de alta en esta compañía sin una reincorporación de identidad, que el
    addendum RTE02-A01 difiere explícitamente. Su propia guía operativa lo dice:
    si alguien puede volver, se **desactiva**, no se borra.
    """

    __tablename__ = "user_company"
    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_company_user_company"),
        ForeignKeyConstraint(
            ["role_id", "company_id"],
            ["role.id", "role.company_id"],
            name="fk_user_company_role_same_company",
            ondelete="RESTRICT",
        ),
        Index("ix_user_company_role_id", "role_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Sin `ForeignKey` propia: la integridad la aporta la FK compuesta de
    # `__table_args__`, que además exige que el rol sea de esta compañía.
    role_id = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<UserCompany user_id={self.user_id} company_id={self.company_id} "
            f"role_id={self.role_id}>"
        )


class CompanyState(TimeStampedModel, IsActiveMixin):
    """Estado de EE.UU. en el que opera una compañía.

    `region` es el catálogo global de estados; esta tabla dice en cuáles opera
    este tenant. Uno de ellos es la sede principal — en el sistema anterior ese
    concepto estaba cableado como la constante `HUB_STATE_CODE = 'GA'`, y aquí
    se modela como dato para que sea configurable.

    `uq_company_state_single_main` es un índice único **parcial**: solo cuenta
    las filas activas marcadas como principales, así que la base impide que una
    compañía tenga dos sedes principales a la vez. Antes eso dependía de que
    `set_main_state` no se ejecutara dos veces en paralelo (AUD-DB-008).
    """

    __tablename__ = "company_state"
    __table_args__ = (
        UniqueConstraint("company_id", "state_id", name="uq_company_state_company_state"),
        Index(
            "uq_company_state_single_main",
            "company_id",
            unique=True,
            postgresql_where=text("is_main AND is_active"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state_id = Column(
        Integer,
        ForeignKey("region.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_main = Column(Boolean, nullable=False, server_default=text("false"))

    state = relationship("Region", lazy="joined")
