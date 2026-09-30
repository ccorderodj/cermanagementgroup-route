"""Una asignacion de vehiculo no puede durar cero (RTE06 cierre, hueco de CP0).

Revision ID: 0012_no_empty_period
Revises: 0011_strict_missing_fact
Create Date: 2026-09-30

Que se colaba, medido
---------------------
`ex_vehicle_assignment_no_overlap` usa `tstzrange(..., '[)')`, y un rango vacio
—`effective_to = effective_from`— **no solapa con nada**, asi que la restriccion
no puede verlo. Eso deja una grieta en el camino concurrente:

    dos `assign(desde = t)` a la vez, sin asignacion previa
      peticion A: no hay anterior, inserta [t, inf)
      peticion B: lee la de A, la cierra en `effective_to = t`
                  -> la fila de A pasa a ser [t, t), que es VACIA
                  -> inserta [t, inf)  y EXCLUDE no protesta

Resultado medido en este repositorio:

    codigos: [200, 200]
    id=1 vehicle=1 from=...693463 to=...693463  vacio=True
    id=2 vehicle=2 from=...693463 to=NULL       vacio=False

Lo encontro el test de concurrencia de CP0, que pasaba de forma intermitente
segun como cayera el orden de las dos peticiones.

Que consecuencia tiene, y cual no
---------------------------------
**El vehiculo aplicable sigue siendo determinista.** `effective_at` exige
`effective_from <= T AND effective_to > T`, que es falso para un rango vacio, asi
que la fila fantasma nunca se resuelve como vigente y ninguna jornada arranco con
el vehiculo equivocado.

Lo que si rompe es el registro: queda una fila que afirma "este vehiculo estuvo
asignado desde t hasta t", es decir nunca. El historial deja de poder leerse tal
cual, que es justamente para lo que existe.

La correccion
-------------
`ck_vehicle_assignment_period` pasa de `>=` a `>`: cerrar una asignacion en su
propio instante de inicio deja de ser posible. En el camino concurrente eso hace
que el `UPDATE` de la segunda peticion falle, y entonces sobrevive exactamente
una, que es lo que el invariante de §8.3 pretendia desde el principio.

Lo unico que se pierde es la posibilidad de registrar una asignacion de duracion
cero, y eso no es un hecho de negocio: nadie condujo un vehiculo durante cero
tiempo.

Datos existentes
----------------
Las filas vacias que hubiera **se borran**, y el motivo esta en el parrafo de
arriba: un intervalo vacio no afirma ningun hecho, asi que borrarlo no pierde
informacion. Lo que ocurrio de verdad —quien asigno, cuando, y quien cerro—
sigue en `audit_event`, que es append-only y no se toca.

La migracion **cuenta** las que borra y lo dice en su log. Si el numero no es
cero en un entorno compartido, merece una mirada: significa que ese tenant paso
por la carrera.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_no_empty_period"
down_revision: Union[str, None] = "0011_strict_missing_fact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT = "ck_vehicle_assignment_period"


def upgrade() -> None:
    conexion = op.get_bind()

    vacias = conexion.execute(
        sa.text(
            "SELECT count(*) FROM vehicle_assignment "
            "WHERE effective_to IS NOT NULL AND effective_to = effective_from"
        )
    ).scalar()

    if vacias:
        conexion.execute(
            sa.text(
                "DELETE FROM vehicle_assignment "
                "WHERE effective_to IS NOT NULL AND effective_to = effective_from"
            )
        )
    print(
        f"0012 | asignaciones de duracion cero borradas: {vacias} "
        "(no afirmaban ningun hecho; la traza sigue en audit_event)"
    )

    op.drop_constraint(CONSTRAINT, "vehicle_assignment", type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        "vehicle_assignment",
        "effective_to IS NULL OR effective_to > effective_from",
    )


def downgrade() -> None:
    # Se vuelve a admitir la igualdad. No se recrean las filas borradas: no
    # habia nada que recrear.
    op.drop_constraint(CONSTRAINT, "vehicle_assignment", type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        "vehicle_assignment",
        "effective_to IS NULL OR effective_to >= effective_from",
    )
