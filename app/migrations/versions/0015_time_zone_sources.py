"""La zona horaria IANA de la jornada y el override del supervisor (T-1/T-2).

Revision ID: 0015_time_zone_sources
Revises: 0014_recovery_accuracy
Create Date: 2026-10-09

Qué hueco cierra
----------------
El sistema sólo conocía el **desfase** del dispositivo (`-240`), no su zona
(`America/New_York`). Un desfase fecha bien un instante concreto, pero no dice
cuándo cambia el horario: el 1 de noviembre de 2026 el Este pasa a `-300`, y
cualquier regla que extrapolara el desfase guardado daría una hora de error. Y
el «hoy» de toda la compañía lo decidía la última jornada de cualquier
supervisor.

Las dos columnas, aprobadas por el PO (D1, opción A adaptada)
--------------------------------------------------------------
* `supervisor_profile.operational_time_zone` — override **opcional** que fija un
  administrador para una excepción. Vacío por defecto: la zona sale sola del
  dispositivo.
* `work_session.start_time_zone` — la zona **efectiva** que se aplicó al iniciar
  la jornada: el override si lo había, la del dispositivo si no. Es la misma
  zona que fecha `session_date` y la que formatea las horas de esa jornada, así
  que no pueden contradecirse. Instantánea inmutable: cambiar el perfil después
  no reescribe ninguna jornada.

Datos existentes
----------------
**No se lee ni se escribe ninguna fila** (D6: sin asignaciones masivas). Las
jornadas anteriores quedan con `start_time_zone` nulo y conservan su
`start_utc_offset_minutes`, que es lo que se muestra de ellas, rotulado como
desfase y no como zona (D5). Atribuirles una zona IANA sería inventar un dato
que no se registró.

`VARCHAR(64)`: el identificador IANA más largo tiene 30 caracteres. La validez
la comprueba la aplicación contra `zoneinfo`, que es la fuente de verdad de las
reglas; un `CHECK` en la base no puede consultar esa lista.

La bajada
---------
Elimina las dos columnas. Se pierde lo capturado desde la subida —las zonas de
las jornadas nuevas y los overrides—, que es exactamente lo que esta migración
añadió; ningún dato anterior depende de ellas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_time_zone_sources"
down_revision = "0014_recovery_accuracy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supervisor_profile",
        sa.Column("operational_time_zone", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "work_session",
        sa.Column("start_time_zone", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_session", "start_time_zone")
    op.drop_column("supervisor_profile", "operational_time_zone")
