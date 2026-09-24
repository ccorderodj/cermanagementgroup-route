"""
Listas configurables por el administrador del tenant.

La distinción que sostiene este módulo, y que es fácil de romper:

* **El código de lista es producto.** Las ocho listas las fijó CER en el
  baseline V0.7; no se añaden ni se quitan desde una pantalla. Por eso son un
  `BusinessEnum` con su `CHECK` en la base.
* **Los valores dentro de cada lista son datos del tenant.** "Completed",
  "Follow-up Required" y demás son ejemplos de datos configurados, no reglas
  del sistema. Por eso son filas, y por eso **Outcome no es un enum** — la
  decisión A-3 del cierre de RTE01 lo dice de forma explícita.

Lo que este módulo deliberadamente NO hace: catálogos para los campos que CER
liberó a texto libre (destino de visita, área de reclutamiento, referencia de
empleado, oficina, área de "Other"). Convertirlos en filas de aquí sería
reintroducir exactamente lo que se quitó.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.core.enums import BusinessEnum
from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.SoftDelete import SoftDeleteMixin
from app.core.models.TimeStamped import TimeStampedModel
from app.core.models.Versioned import VersionedMixin


class StandardValueList(BusinessEnum):
    """Las ocho listas aprobadas. Cerradas: las define el producto, no el tenant."""

    CLIENT_VISIT_ACTIVITIES = "client_visit_activities"
    RECRUITING_ACTIVITIES = "recruiting_activities"
    EMPLOYEE_VISIT_REASONS = "employee_visit_reasons"
    DELIVERY_TYPES = "delivery_types"
    OFFICE_PURPOSES = "office_purposes"
    OTHER_ACTIVITIES = "other_activities"
    OUTCOMES = "outcomes"
    RECEIVED_BY = "received_by"


class StandardValue(TimeStampedModel, IsActiveMixin, SoftDeleteMixin, VersionedMixin):
    """Un valor seleccionable de una de las ocho listas, propiedad del tenant.

    Tres estados, no dos (RTE02-A01)
    ---------------------------------
    * **Activo** — se ofrece en los formularios operativos.
    * **Desactivado** (`is_active = False`) — retirado del uso, pero visible en
      la administración al pedir los inactivos, y reactivable.
    * **Borrado** (`deleted_at`) — fuera de la experiencia normal: no aparece ni
      entre los activos ni entre los inactivos, ni en ningún selector.

    En los tres casos la fila sigue existiendo. Una actividad de marzo guardó el
    `standard_value_id` que eligió, y ese identificador tiene que seguir
    resolviendo a "Safety Follow-up" en septiembre aunque el administrador haya
    borrado la opción entretanto. Ver `app/core/models/SoftDelete.py`.

    Etiquetas repetidas
    -------------------
    `uq_standard_value_company_list_label` las une por compañía **y** por lista.
    Dos tenants pueden llamar igual a sus valores sin verse; dentro de un tenant,
    "Completed" puede existir a la vez en Outcomes y en Delivery Types, porque
    son listas distintas. Lo único que se impide es duplicarla dentro de la
    misma lista del mismo tenant, que es la que haría ambigua la elección.

    Es **parcial** (`WHERE deleted_at IS NULL`) desde RTE02-A01: si contara las
    filas borradas, retirar "Escalated" impediría volver a crearlo, y el
    administrador chocaría contra una fila que para él ya no existe.

    `seed_key`: por qué una columna y no una comparación de etiquetas
    -----------------------------------------------------------------
    El aprovisionamiento inicial tiene que ser idempotente en un sentido
    exigente: re-ejecutarlo no puede duplicar, **ni resucitar lo que el
    administrador borró, ni revertir un renombrado, ni reactivar lo que
    desactivó**. Comparar por etiqueta no lo consigue —en cuanto alguien
    renombra "Escalated" a "Escalated to Manager", la siguiente siembra ya no lo
    reconoce y crea un duplicado—. `seed_key` es la identidad estable del valor
    sembrado: sobrevive al renombrado, a la desactivación y a la lápida, y es lo
    único que el aprovisionador mira para decidir si ya hizo su trabajo.

    Es `NULL` para todo lo que cree el administrador: esos valores no son de
    nadie más que del tenant, y nunca deben ser tocados por una siembra.
    """

    __tablename__ = "standard_value"
    __table_args__ = (
        StandardValueList.check("list_code", name="ck_standard_value_list_code"),
        # Parcial: una etiqueta borrada deja de ocupar sitio (ver docstring).
        Index(
            "uq_standard_value_company_list_label",
            "company_id",
            "list_code",
            "label",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Esta, en cambio, **no** es parcial a propósito: la huella de la
        # siembra tiene que sobrevivir al borrado, porque es justo lo que impide
        # resucitar un valor que el administrador quitó.
        UniqueConstraint(
            "company_id", "seed_key", name="uq_standard_value_company_seed_key"
        ),
        UniqueConstraint("id", "company_id", name="uq_standard_value_id_company"),
        CheckConstraint("sort_order >= 0", name="ck_standard_value_sort_order"),
        # El acceso normal es "dame los valores activos de esta lista, en orden".
        Index(
            "ix_standard_value_company_list",
            "company_id",
            "list_code",
            "sort_order",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    list_code = Column(String(40), nullable=False)
    label = Column(String(120), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    #: Identidad estable del valor sembrado, `NULL` si lo creó el administrador.
    #: Nunca se muestra ni se acepta desde la API: es huella de siembra, no dato
    #: de negocio.
    seed_key = Column(String(80), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<StandardValue id={self.id} list={self.list_code} "
            f"label={self.label!r} company_id={self.company_id}>"
        )
