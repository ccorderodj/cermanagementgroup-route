"""El motivo de Missing para un punto recuperado demasiado impreciso (F-1).

Revision ID: 0014_recovery_accuracy
Revises: 0013_client_action_key
Create Date: 2026-10-01

Que hueco cierra
----------------
La etapa de recuperacion aceptaba **cualquier** precision, mientras `fresh`
exigia 100 m y `degraded_cached` 500 m mas la edad. Un punto rechazado en la
etapa 1 por tener dos kilometros de error entraba en la 3 como `recovered`, que
es un nivel de evidencia de pleno derecho, y `for_trip_waypoints()` no vuelve a
filtrar por nivel ni por precision: acababa siendo un waypoint oficial de
kilometraje.

Corregido en el cliente, la recuperacion ahora puede agotar su ventana habiendo
visto puntos y habiendolos rechazado **todos** por calidad. Ese hecho no lo
describe ningun motivo existente.

Por que un motivo nuevo y no reutilizar uno
-------------------------------------------
`recovery_window_exhausted` dice literalmente "la ventana termino sin punto y
sin mas informacion". Aqui si hubo puntos. Usar ese motivo convertiria dos
hechos distintos —un GPS que no fija y un GPS que fija mal— en la misma fila, y
quien calibre los umbrales con datos de campo (V-2, V-5) no podria separarlos:
el primero pide mas ventana, el segundo pide revisar el umbral. Son acciones
opuestas.

D-FIELD-03 autoriza el motivo nuevo cuando ninguno existente representa el
hecho con precision, y prohibe sobrecargar uno ajeno.

Datos existentes
----------------
**No se lee ni se escribe ninguna fila.** Solo se reemplaza la restriccion por
otra que admite un valor mas, asi que toda fila que pasaba la anterior pasa la
nueva. Ampliar un `CHECK` nunca puede invalidar lo que ya estaba.

La bajada
---------
`missing_location_event` es append-only por disparador: no se pueden reescribir
ni borrar sus filas. Asi que una bajada con filas que usen el motivo nuevo no
puede "arreglarlas", y restringir el `CHECK` con esas filas dentro **fallaria**
con un error de PostgreSQL que no explica nada.

Por eso la bajada comprueba antes y **se niega con un mensaje que dice cuantas
filas estorban y como consultarlas**. Es el mismo patron que la 0011: fallar
pronto y en claro, en vez de a medias y en jerga.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_recovery_accuracy"
down_revision: Union[str, None] = "0013_client_action_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOMBRE = "ck_missing_location_reason"
TABLA = "missing_location_event"

#: Los seis de siempre.
ANTERIORES = (
    "permission_denied",
    "position_unavailable",
    "acquisition_timeout",
    "cached_rejected",
    "recovery_window_exhausted",
    "no_client_report",
)
#: El septimo. Va en medio, junto a los otros de recuperacion, para que la
#: lista se lea en el orden del camino escalonado.
NUEVO = "recovery_accuracy_rejected"


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


def upgrade() -> None:
    op.drop_constraint(NOMBRE, TABLA, type_="check")
    op.create_check_constraint(
        NOMBRE,
        TABLA,
        f"reason_code IN ({_lista(ANTERIORES + (NUEVO,))})",
    )


def downgrade() -> None:
    conexion = op.get_bind()
    cuantas = conexion.execute(
        sa.text(
            f"SELECT count(*) FROM {TABLA} WHERE reason_code = :motivo"
        ),
        {"motivo": NUEVO},
    ).scalar_one()

    if cuantas:
        raise RuntimeError(
            f"No se puede bajar: hay {cuantas} fila(s) de {TABLA} con "
            f"reason_code = '{NUEVO}', y la tabla es append-only, asi que no "
            f"se pueden reescribir ni borrar.\n\n"
            f"Para verlas:\n"
            f"    SELECT id, company_id, event_kind, subject_id, occurred_at\n"
            f"    FROM {TABLA} WHERE reason_code = '{NUEVO}';\n\n"
            f"Bajar con esas filas dentro exigiria decidir que motivo falso "
            f"ponerles, y eso seria reescribir un hecho."
        )

    op.drop_constraint(NOMBRE, TABLA, type_="check")
    op.create_check_constraint(
        NOMBRE, TABLA, f"reason_code IN ({_lista(ANTERIORES)})"
    )
