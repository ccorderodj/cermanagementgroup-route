"""Registro productivo de envíos de correos de actividad (RTE-MAIL-CP4-01/02).

Revision ID: 0024_activity_email_delivery
Revises: 0023_strategic_reports
Create Date: 2026-10-19

Qué añade
---------
`activity_email_delivery`: una fila por correo real que tocaba o se pidió
(tipo, destinatario, día operativo), con su estado y sus intentos. La clave
única `(company_id, recipient_user_id, report_type, operational_date)` la
comparten el programador interno, el cron de DigitalOcean y el botón «Send now»:
el mismo correo del mismo día no puede salir dos veces.

No es `mail_test_send` (sólo pruebas con datos ficticios), y no guarda asunto,
cuerpo, notas ni texto del proveedor.

No escribe filas: nada queda programado al migrar.

La bajada
---------
Borra la tabla. La auditoría de cada envío sigue en `audit_event`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_activity_email_delivery"
down_revision = "0023_strategic_reports"
branch_labels = None
depends_on = None

_TIPOS = "'midday_motivation', 'end_of_day_recognition', 'strategic_midday_report', 'strategic_end_of_day_report'"
_ESTADOS = (
    "'pending', 'claimed', 'accepted_by_provider', 'retryable_failure', "
    "'permanent_failure', 'skipped', 'unknown_outcome'"
)


def upgrade() -> None:
    op.create_table(
        "activity_email_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("report_type", sa.String(40), nullable=False),
        sa.Column("operational_date", sa.Date(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_backend", sa.String(40), nullable=True),
        sa.Column("reason_code", sa.String(60), nullable=True),
        sa.Column(
            "requested_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("request_reason", sa.String(300), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "company_id", "recipient_user_id", "report_type", "operational_date",
            name="uq_activity_email_delivery_key",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_activity_email_delivery_membership",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"report_type IN ({_TIPOS})", name="ck_activity_email_delivery_type"),
        sa.CheckConstraint(f"status IN ({_ESTADOS})", name="ck_activity_email_delivery_status"),
        sa.CheckConstraint("source IN ('schedule', 'reconcile', 'manual')", name="ck_activity_email_delivery_source"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_activity_email_delivery_attempts"),
    )
    op.create_index("ix_activity_email_delivery_recipient_user_id", "activity_email_delivery", ["recipient_user_id"])
    op.create_index("ix_activity_email_delivery_status_due", "activity_email_delivery", ["status", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_email_delivery_status_due", table_name="activity_email_delivery")
    op.drop_index("ix_activity_email_delivery_recipient_user_id", table_name="activity_email_delivery")
    op.drop_table("activity_email_delivery")
