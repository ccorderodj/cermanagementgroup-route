"""Aviso de captura periódica: una sola vez por persona (RTE-LOC-02).

Revision ID: 0029_location_notice_ack
Revises: 0028_periodic_location_capture
Create Date: 2026-10-20

Qué añade
---------
`location_notice_ack`: que una persona vio el aviso «CER Route records your
location periodically…», con la versión del texto y la hora. Sustituye a la
frase fija de My Route, que se repetía cada día. No se rellena nada: quien
tenga la jornada abierta con la captura encendida lo verá una vez.

La bajada
---------
Borra la tabla; el aviso volvería a mostrarse una vez a cada persona.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_location_notice_ack"
down_revision = "0028_periodic_location_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_notice_ack",
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("notice_version", sa.Integer(), primary_key=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id", "company_id"], ["user_company.user_id", "user_company.company_id"],
            name="fk_location_notice_ack_membership", ondelete="CASCADE",
        ),
        sa.CheckConstraint("notice_version >= 1", name="ck_location_notice_ack_version"),
    )


def downgrade() -> None:
    op.drop_table("location_notice_ack")
