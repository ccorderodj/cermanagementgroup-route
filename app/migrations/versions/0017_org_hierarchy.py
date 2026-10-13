"""Jerarquía organizacional de CER Route: cargo y superior por periodo.

Revision ID: 0017_org_hierarchy
Revises: 0016_rte09_reports_fuel
Create Date: 2026-10-13

Qué añade
---------
* `org_assignment`: el cargo y el superior de cada persona en una compañía,
  una fila por periodo `[valid_from, valid_to)` (ver `organization/models.py`).
* El rol de producto `route_manager` **vacío** en cada compañía que no lo
  tenga. Sus capacidades las concede la alineación del catálogo
  (`align_role_capabilities`, parte de *converge*), como a cualquier rol por
  defecto: la migración no concede nada a nadie y **no asigna el rol a ninguna
  persona**.

Datos existentes
----------------
**Ninguna asignación se rellena** (D-4). Nadie tiene cargo ni superior tras la
subida; la estructura la carga expresamente un administrador autorizado. Las
jornadas históricas no se tocan.

La bajada
---------
Borra la tabla —se pierde la estructura cargada desde la subida, que es lo que
esta migración añadió— y los roles `route_manager` **sin miembros**. Si alguna
persona ya tiene ese rol, la bajada se detiene en vez de dejarla sin rol: hay que
reasignarla antes. `btree_gist` no se retira (la usa la 0009).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_org_hierarchy"
down_revision = "0016_rte09_reports_fuel"
branch_labels = None
depends_on = None

POSICIONES = "'ceo', 'coo', 'regional_manager', 'osm', 'supervisor'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "org_assignment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.String(length=30), nullable=False),
        sa.Column("superior_user_id", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"position IN ({POSICIONES})", name="ck_org_assignment_position"),
        sa.CheckConstraint(
            "superior_user_id IS NULL OR superior_user_id <> user_id",
            name="ck_org_assignment_not_self",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from", name="ck_org_assignment_period"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_org_assignment_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superior_user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_org_assignment_superior_member",
            ondelete="RESTRICT",
        ),
    )
    op.execute(
        """
        ALTER TABLE org_assignment
        ADD CONSTRAINT ex_org_assignment_no_overlap
        EXCLUDE USING gist (
            company_id WITH =,
            user_id WITH =,
            tstzrange(valid_from, valid_to, '[)') WITH &&
        )
        """
    )
    op.create_index(
        "uq_org_assignment_current",
        "org_assignment",
        ["company_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_org_assignment_superior_current",
        "org_assignment",
        ["company_id", "superior_user_id"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # El rol, vacío, donde falte. Sin capacidades ni miembros.
    op.execute(
        """
        INSERT INTO role (company_id, name, description, category, is_active,
                          created_at, updated_at)
        SELECT c.id, 'route_manager',
               'CER Route manager (CEO, COO, Regional Manager); sees and manages only their branch',
               'operative', true, now(), now()
        FROM company AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM role AS r WHERE r.company_id = c.id AND r.name = 'route_manager'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_org_assignment_superior_current", table_name="org_assignment")
    op.drop_index("uq_org_assignment_current", table_name="org_assignment")
    op.drop_table("org_assignment")
    # Sólo los roles sin miembros: con miembros, la FK RESTRICT detiene la bajada.
    op.execute(
        """
        DELETE FROM role_permission WHERE role_id IN (
            SELECT id FROM role WHERE name = 'route_manager'
        )
        """
    )
    op.execute("DELETE FROM role WHERE name = 'route_manager'")
