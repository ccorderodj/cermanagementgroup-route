"""Quién sustituyó a quién en la jerarquía (V1.5).

Revision ID: 0020_org_replaces_user
Revises: 0019_org_single_ceo
Create Date: 2026-10-14

Qué añade
---------
`org_assignment.replaces_user_id`: en la fila que abre «Replace manager» para
el sucesor, la persona a la que sustituye. Con ese enlace el alcance hace que
**la historia siga al puesto**: el sucesor ve lo que veía su antecesor (V1.5).

* Nulo en todas las filas existentes: ninguna sustitución anterior se infiere.
  Las que se hicieron con V1.4 quedan en `audit_event` (`org_succession`), pero
  reconstruirlas sería interpretar datos; no se hace.
* Clave foránea a `user.id` con `SET NULL`: si la identidad desapareciera, la
  asignación del sucesor sigue siendo válida y sólo pierde la herencia.
* Nadie se sustituye a sí mismo (CHECK).

No toca usuarios, roles, capacidades, Estado operativo ni Zona horaria.

La bajada
---------
Quita la columna. La herencia de historia deja de existir; las asignaciones,
no cambian.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_org_replaces_user"
down_revision = "0019_org_single_ceo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("org_assignment", sa.Column("replaces_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_org_assignment_replaces_user",
        "org_assignment",
        "user",
        ["replaces_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_org_assignment_replaces_not_self",
        "org_assignment",
        "replaces_user_id IS NULL OR replaces_user_id <> user_id",
    )


def downgrade() -> None:
    op.drop_constraint("ck_org_assignment_replaces_not_self", "org_assignment", type_="check")
    op.drop_constraint("fk_org_assignment_replaces_user", "org_assignment", type_="foreignkey")
    op.drop_column("org_assignment", "replaces_user_id")
