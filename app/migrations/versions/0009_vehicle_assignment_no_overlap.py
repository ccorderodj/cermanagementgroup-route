"""Dos asignaciones de vehículo no pueden estar vigentes a la vez (RTE06-CP0, E5).

Revision ID: 0009_assignment_no_overlap
Revises: 0008_activity_execution
Create Date: 2026-09-29

Qué se estaba colando
---------------------
`uq_vehicle_assignment_current` es un índice único **parcial**
(`WHERE effective_to IS NULL`) y sólo impide dos asignaciones *abiertas*. El
resto lo comprobaba Python, de forma incompleta. Este caso pasaba las tres
protecciones sin necesidad de concurrencia:

    existe:  [Mar 1 → Abr 1)   cerrada
    no hay:  ninguna abierta

    assign(effective_from = Feb 1)
      → la comprobación buscaba `from <= Feb 1 AND to > Feb 1`;
        la de marzo empieza el Mar 1, así que no la encontraba
      → insertaba [Feb 1 → ∞), que solapa [Mar 1 → Abr 1)

Resultado: el 15 de marzo había dos asignaciones aplicables, y
`VehicleAssignmentsDAO.effective_at()` devolvía una de las dos según el plan de
ejecución. El vehículo con el que se abría una jornada dejaba de ser
determinista, y ése es el dato que §8 de RTE06 exige fijar antes de construir
nada encima.

Por qué `EXCLUDE` y no un disparador
------------------------------------
El patrón de esta base para invariantes es el disparador PL/pgSQL
(`*_is_append_only`), pero aquí no sirve: dos inserciones concurrentes no se ven
la una a la otra, así que un disparador necesitaría bloqueo explícito para ser
correcto — y sería reimplementar a mano lo que `EXCLUDE` ya hace bien.

`EXCLUDE USING gist` es correcto por construcción y atómico frente a
concurrencia, así que además elimina el TOCTOU que tenía la comprobación en
Python (leía fuera de la transacción).

El intervalo es semiabierto, `[from, to)`
-----------------------------------------
Es lo que hace que la reasignación normal siga funcionando. Reasignar cierra la
anterior en `effective_to = desde` y abre la nueva en `effective_from = desde`:
con `[)` esos dos intervalos **se tocan pero no solapan**. Con `[]` toda
reasignación del producto habría empezado a fallar.

Un intervalo vacío (`effective_to = effective_from`, que el CHECK permite) no
solapa con nada, por definición de `tstzrange`.

La extensión
------------
`btree_gist` hace falta para poder combinar `=` sobre enteros con `&&` sobre un
rango en el mismo índice GiST. Desde PostgreSQL 13 es una extensión *trusted*:
la instala el dueño de la base sin superusuario. Verificado en este entorno
(PostgreSQL 16.4, `pg_available_extensions.trusted = true`).

Datos existentes
----------------
No se transforma ni se interpreta nada. La restricción se añade con los datos
tal como están: si alguna compañía ya tuviera un solapamiento creado por el
hueco de arriba, `ALTER TABLE` **falla** y la migración se detiene. Eso es lo
correcto — un dato de negocio ambiguo no se corrige en silencio para que la
migración termine. Si ocurre, hay que decidir por compañía qué asignación vale,
y esa decisión no es de esta migración.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_assignment_no_overlap"
down_revision: Union[str, None] = "0008_activity_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT = "ex_vehicle_assignment_no_overlap"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        f"""
        ALTER TABLE vehicle_assignment
        ADD CONSTRAINT {CONSTRAINT}
        EXCLUDE USING gist (
            company_id WITH =,
            supervisor_profile_id WITH =,
            tstzrange(effective_from, effective_to, '[)') WITH &&
        )
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE vehicle_assignment DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    # La extensión no se retira: otra cosa puede haberla instalado o necesitarla,
    # y `DROP EXTENSION` se llevaría por delante cualquier índice que la use.
