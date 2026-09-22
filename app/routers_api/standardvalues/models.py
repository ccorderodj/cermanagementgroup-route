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
)

from app.core.enums import BusinessEnum
from app.core.models.IsActiveMixin import IsActiveMixin
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


class StandardValue(TimeStampedModel, IsActiveMixin, VersionedMixin):
    """Un valor seleccionable de una de las ocho listas, propiedad del tenant.

    Ciclo de vida seguro para la historia
    -------------------------------------
    Un valor **no se borra**: se desactiva. Una actividad de marzo guarda el
    `standard_value_id` que eligió, y ese identificador tiene que seguir
    resolviendo a "Safety Follow-up" en septiembre aunque el administrador haya
    retirado la opción del formulario entretanto. Borrar la fila dejaría un
    informe histórico hablando de un valor que ya no existe.

    Etiquetas repetidas
    -------------------
    `uq_standard_value_company_list_label` las une por compañía **y** por lista.
    Dos tenants pueden llamar igual a sus valores sin verse; dentro de un tenant,
    "Completed" puede existir a la vez en Outcomes y en Delivery Types, porque
    son listas distintas. Lo único que se impide es duplicarla dentro de la
    misma lista del mismo tenant, que es la que haría ambigua la elección.
    """

    __tablename__ = "standard_value"
    __table_args__ = (
        StandardValueList.check("list_code", name="ck_standard_value_list_code"),
        UniqueConstraint(
            "company_id",
            "list_code",
            "label",
            name="uq_standard_value_company_list_label",
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

    def __repr__(self) -> str:
        return (
            f"<StandardValue id={self.id} list={self.list_code} "
            f"label={self.label!r} company_id={self.company_id}>"
        )
