"""
Borrado que no destruye historia.

Por qué existe
--------------
`is_active` y `deleted_at` responden preguntas distintas, y confundirlas fue
justo lo que motivó el addendum RTE02-A01:

* **Desactivar** retira algo del uso operativo sin sacarlo de la administración.
  El administrador lo sigue viendo al pedir los inactivos, y puede reactivarlo.
* **Borrar** lo saca de la experiencia normal de administración: deja de
  aparecer en las listas de activos y de inactivos, y en los selectores.

Lo que **no** cambia es la historia. Una jornada de marzo guardó el
`vehicle_id` que usó, y ese identificador tiene que seguir resolviendo a "V-014"
en septiembre aunque el administrador haya borrado el vehículo entretanto. Por
eso la fila se marca en vez de destruirse: es una lápida, no una papelera.

Además, la base ya lo impone: `vehicle_assignment.vehicle_id` y
`work_session.vehicle_id` son claves foráneas con `RESTRICT`, así que un
`DELETE` físico de un vehículo con historia lo rechaza PostgreSQL; y
`vehicle_assignment.supervisor_profile_id` es `CASCADE`, así que borrar
físicamente un perfil se llevaría por delante su historial de asignaciones. El
borrado físico no era una opción disponible, no una que se descartara por gusto.

La regla que acompaña a este mixin
----------------------------------
**Toda consulta de la experiencia normal filtra `deleted_at IS NULL`.** Si un
registro con lápida reaparece en una pantalla de administración o en un
selector, el mixin no se está usando bien: el addendum pide explícitamente que
la estrategia de persistencia no se filtre a la interfaz.

Y una consecuencia que es fácil pasar por alto: cualquier restricción **única**
de la tabla —la unidad de un vehículo, la etiqueta de un valor— tiene que
volverse **parcial** (`WHERE deleted_at IS NULL`). Si no, borrar "V-014"
impediría volver a crear otro "V-014" para siempre, y el administrador vería
un conflicto contra una fila que para él ya no existe.
"""

from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func

from app.database import Base


class SoftDeleteMixin(Base):
    """`deleted_at`: cuándo se retiró de la administración, o `NULL` si sigue ahí."""

    __abstract__ = True

    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Marca la lápida con el reloj de la base, nunca con uno del cliente."""
        self.deleted_at = func.now()
