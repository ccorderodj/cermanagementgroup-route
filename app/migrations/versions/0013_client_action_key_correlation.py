"""La clave de accion del cliente, en la fila de dominio (RTE06 cierre final).

Revision ID: 0013_client_action_key
Revises: 0012_no_empty_period
Create Date: 2026-09-30

Que hueco cierra
----------------
La correlacion de §14 es un id **que crea el servidor**, asi que una accion
encolada sin red no tiene todavia nada a lo que atar su punto de ubicacion. El
cierre anterior lo resolvia difiriendo el sujeto y resolviendolo al reconectar,
**y negandose a atar cuando habia dos acciones del mismo tipo pendientes**. Eso
era veraz pero dejaba puntos validos convertidos en Missing por ambiguedad, que
es lo que la revision de CER marco como `NOT IMPLEMENTED / GAP`.

La cadena de identidad, ahora completa
--------------------------------------
    id de accion del cliente  (ya existe: `PendingAction.id`)
      -> cabecera `Idempotency-Key`  (ya existe)
      -> `client_action_key` en la fila que la accion crea   <- esto es nuevo
      -> `location_fix.subject_id`

El cliente ya generaba una clave durable por accion y ya la enviaba como
`Idempotency-Key`. Lo unico que faltaba era que la fila creada **se quedara con
ella**, y entonces el punto puede decir "pertenezco a la accion K" en vez de
"pertenezco a la fila 42", que offline no se puede saber.

Es la extension mas pequena posible: ninguna tabla nueva, ningun mecanismo
nuevo, ninguna segunda maquina de estados. Tres columnas.

La clave es un identificador, no autoridad
------------------------------------------
§12 lo exige y el servicio lo cumple: el servidor resuelve la fila por
`(company_id, client_action_key)` y **despues** aplica la misma comprobacion de
propiedad que ya aplicaba —el sujeto tiene que pertenecer a la jornada del
supervisor autenticado—. Un cliente que invente una clave ajena no obtiene nada
que no obtuviera inventando un `subject_id` ajeno: 404.

Los unicos parciales, y por que
-------------------------------
`uq_*_client_action_key` es unico **parcial** (`WHERE client_action_key IS NOT
NULL`). Las filas anteriores a esta migracion no tienen clave y no se les puede
inventar una, asi que quedan en `NULL`; un unico completo las haria colisionar
entre si. Y el parcial es lo que hace que un reenvio no pueda crear una segunda
fila con la misma clave, que es la idempotencia del §5.9 garantizada por la
base y no por el codigo.

Datos existentes
----------------
Tres columnas nuevas, anulables. **No se lee ni se escribe ninguna fila
existente.** Las jornadas, viajes y cambios de plan anteriores se quedan con
`client_action_key = NULL`, que es lo cierto: se crearon sin que nadie
registrara la clave. Inventarles una seria fabricar un hecho.

La consecuencia practica es que la evidencia de ubicacion para una fila antigua
se sigue enviando por `subject_id`, que es el camino que siempre ha funcionado
cuando hay red. Los dos caminos conviven a proposito.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_client_action_key"
down_revision: Union[str, None] = "0012_no_empty_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Las tres filas que una accion del ciclo de vida **crea** y a las que un punto
#: de ubicacion necesita poder referirse antes de conocer su id.
#:
#: `activity_execution` no esta, y no es un olvido: se crea por
#: `activity/start`, que hoy **no se encola** sin red. Si la accion no puede
#: ocurrir offline, su evidencia tampoco, asi que no hay nada que correlacionar.
#: El mecanismo se extiende con una columna mas el dia que esa accion sea
#: encolable.
TABLAS: tuple[str, ...] = ("work_session", "trip", "trip_purpose_change")


def upgrade() -> None:
    for tabla in TABLAS:
        op.add_column(
            tabla,
            sa.Column("client_action_key", sa.String(length=64), nullable=True),
        )
        op.create_index(
            f"uq_{tabla}_client_action_key",
            tabla,
            ["company_id", "client_action_key"],
            unique=True,
            postgresql_where=sa.text("client_action_key IS NOT NULL"),
        )


def downgrade() -> None:
    for tabla in reversed(TABLAS):
        op.drop_index(f"uq_{tabla}_client_action_key", table_name=tabla)
        op.drop_column(tabla, "client_action_key")
