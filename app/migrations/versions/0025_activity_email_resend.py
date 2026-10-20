"""Reenvío de un correo de actividad que ya salió.

Revision ID: 0025_activity_email_resend
Revises: 0024_activity_email_delivery
Create Date: 2026-10-19

Qué añade
---------
`activity_email_resend`: una fila por reenvío, colgada de la entrega original
(`activity_email_delivery`, que sigue siendo una por persona, tipo y día). La
clave única `(delivery_id, sequence)` impide que un doble clic mande dos
reenvíos. Lo autoriza la capacidad `route.activityemails.resend`, a demanda.

No guarda asunto, cuerpo, notas ni texto del proveedor. No escribe filas.

La bajada
---------
Borra la tabla. La auditoría de cada reenvío sigue en `audit_event`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_activity_email_resend"
down_revision = "0024_activity_email_delivery"
branch_labels = None
depends_on = None

_ESTADOS = (
    "'pending', 'claimed', 'accepted_by_provider', 'retryable_failure', "
    "'permanent_failure', 'skipped', 'unknown_outcome'"
)


def upgrade() -> None:
    op.create_table(
        "activity_email_resend",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "delivery_id", sa.Integer(), sa.ForeignKey("activity_email_delivery.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider_backend", sa.String(40), nullable=True),
        sa.Column("reason_code", sa.String(60), nullable=True),
        sa.Column(
            "requested_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("request_reason", sa.String(300), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("delivery_id", "sequence", name="uq_activity_email_resend_sequence"),
        sa.CheckConstraint(f"status IN ({_ESTADOS})", name="ck_activity_email_resend_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_activity_email_resend_sequence"),
    )
    op.create_index("ix_activity_email_resend_delivery_id", "activity_email_resend", ["delivery_id"])


def downgrade() -> None:
    op.drop_index("ix_activity_email_resend_delivery_id", table_name="activity_email_resend")
    op.drop_table("activity_email_resend")
