"""Un único CEO vigente por compañía (V1.4, FR-02).

Revision ID: 0019_org_single_ceo
Revises: 0018_route_distinct_roles
Create Date: 2026-10-14

Qué añade
---------
Un índice único parcial sobre `org_assignment (company_id)` para las filas con
`position = 'ceo'` y `valid_to IS NULL`. Es la garantía que no depende de que
el servicio se acuerde de comprobarlo: dos altas simultáneas de CEO en el mismo
tenant no pueden quedar las dos.

* Los CEO **históricos** (con `valid_to`) no cuentan: puede haber tantos como
  sustituciones haya habido.
* Un CEO **suspendido** con su cargo abierto sigue ocupando el puesto: la
  suspensión no cierra la asignación.

Preflight: no elige a nadie
---------------------------
Antes de crear el índice se cuentan los CEO vigentes por compañía. Si alguna
tiene más de uno, la migración **se detiene sin cambiar nada** y dice qué
compañías y cuántos. Elegir cuál de ellos es el titular es una decisión de
negocio, no algo que una migración pueda inferir: se regulariza antes, desde
CER Route → Users, y después se migra.

No toca usuarios, roles, capacidades, Estado operativo ni Zona horaria.

La bajada
---------
Quita el índice. No hay datos que deshacer.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0019_org_single_ceo"
down_revision = "0018_route_distinct_roles"
branch_labels = None
depends_on = None

INDICE = "uq_org_assignment_one_ceo"


def upgrade() -> None:
    conexion = op.get_bind()
    duplicados = conexion.execute(
        text(
            "SELECT company_id, count(*) AS n FROM org_assignment "
            "WHERE position = 'ceo' AND valid_to IS NULL "
            "GROUP BY company_id HAVING count(*) > 1 ORDER BY company_id"
        )
    ).all()
    if duplicados:
        detalle = ", ".join(f"company {f.company_id}: {f.n} CEOs" for f in duplicados)
        raise RuntimeError(
            "More than one current CEO in: "
            f"{detalle}. Choose the titular CEO in CER Route → Users "
            "(replace or retire the others) before applying this migration. "
            "Nothing was changed."
        )
    op.create_index(
        INDICE,
        "org_assignment",
        ["company_id"],
        unique=True,
        postgresql_where=text("position = 'ceo' AND valid_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDICE, table_name="org_assignment")
