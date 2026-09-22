"""
Estados de negocio: un enum en Python y un CHECK en la base.

Por qué las dos cosas
---------------------
La regla del repositorio es que un estado de negocio no se escribe como literal
suelto (`AGENTS.md`, regla general 4). El enum evita el literal en el código;
el `CHECK` evita la fila con un estado que nadie escribió a propósito —una
migración de datos, un `UPDATE` manual, un script de importación—. Una
comprobación en Python protege mientras nadie se olvide de llamarla; una de la
base protege siempre.

Escribir las dos listas a mano las desincroniza tarde o temprano, así que la
restricción se **deriva** del enum:

    class WorkOrderStatus(BusinessEnum):
        PENDING_APPROVAL = "pending_approval"
        ACTIVE = "active"
        INACTIVE = "inactive"

    __table_args__ = (
        WorkOrderStatus.check("status", name="ck_work_order_status"),
    )

Los valores son códigos estables, no etiquetas: la interfaz traduce
`pending_approval` a "Pending Approval". Guardar la etiqueta haría que
cambiar un texto de pantalla fuera una migración de datos.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint


class BusinessEnum(StrEnum):
    """Estado de negocio con su restricción de base asociada."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def sql_values(cls) -> str:
        """La lista en literal SQL, para constraints y migraciones."""
        return ", ".join(f"'{value}'" for value in cls.values())

    @classmethod
    def check(cls, column: str, *, name: str) -> CheckConstraint:
        """`CHECK (columna IN (...))` con los valores del enum.

        Se usa en `__table_args__` del modelo, así que Alembic la recoge en el
        autogenerate y la migración la crea sin escribirla dos veces.
        """
        return CheckConstraint(f"{column} IN ({cls.sql_values()})", name=name)


def transition_allowed(
    transitions: dict[str, frozenset[str]],
    *,
    current: str,
    target: str,
) -> bool:
    """Si `current -> target` está en el mapa de transiciones permitidas.

    El mapa vive junto al dominio que lo define. Aquí solo está la consulta,
    para que ningún servicio la reimplemente con su propio `if`.
    """
    return target in transitions.get(current, frozenset())
