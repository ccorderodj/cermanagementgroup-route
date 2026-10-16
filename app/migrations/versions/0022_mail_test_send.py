"""Registro compartido de envíos de prueba de correo (RTE-MAIL-UNIFIED-01, CP1).

Revision ID: 0022_mail_test_send
Revises: 0021_activity_email_settings
Create Date: 2026-10-16

Qué añade
---------
`mail_test_send`: una fila por envío de prueba (proveedor o plantilla) que pasó
las barreras. Es el presupuesto compartido de pruebas por persona y la traza de
su resultado. No guarda asunto, cuerpo ni texto del proveedor.

No escribe filas ni toca ninguna otra tabla.

La bajada
---------
Borra la tabla. La auditoría de los intentos sigue en `audit_event` y
`platform_audit_event`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_mail_test_send"
down_revision = "0021_activity_email_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_test_send",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("target", sa.String(60), nullable=False),
        sa.Column("destination", sa.String(254), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("backend", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("channel IN ('provider', 'template')", name="ck_mail_test_send_channel"),
        sa.CheckConstraint(
            "outcome IN ('pending', 'accepted_by_provider', 'not_sent_development_backend', "
            "'captured_by_test_backend', 'failed_auth', 'failed_unreachable')",
            name="ck_mail_test_send_outcome",
        ),
    )
    op.create_index("ix_mail_test_send_actor_time", "mail_test_send", ["actor_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_test_send_actor_time", table_name="mail_test_send")
    op.drop_table("mail_test_send")
