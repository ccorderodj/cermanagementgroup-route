"""Configuración de los correos de actividad (RTE-NOT-01).

Revision ID: 0021_activity_email_settings
Revises: 0020_org_replaces_user
Create Date: 2026-10-15

Qué añade
---------
* `activity_email_template`: el texto personalizado de cada uno de los dos
  correos, por compañía. Único por `(company_id, template_type)`; tipo cerrado
  por CHECK; asunto de una línea y cuerpo no vacíos, también por CHECK.
* `activity_email_preference`: si una persona es elegible para el correo de
  mediodía y para el de fin de jornada. Único por `(company_id, user_id)`, con
  clave foránea compuesta a `user_company`: nadie de otra compañía.

Qué **no** hace
---------------
No escribe ninguna fila. Ninguna compañía recibe plantillas (usa el texto
aprobado del código hasta que alguien lo personalice) y **nadie queda
suscrito**: los dos interruptores nacen en `false` y no existe preferencia de
nadie hasta que un administrador la active (BR-04).

No envía correos ni programa nada: eso es RTE-NOT-02/03.

La bajada
---------
Borra las dos tablas, y con ellas los textos personalizados y las preferencias.
Los cambios siguen en `audit_event`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_activity_email_settings"
down_revision = "0020_org_replaces_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_email_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_type", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "template_type", name="uq_activity_email_template_company_type"),
        sa.CheckConstraint(
            "template_type IN ('midday_motivation', 'end_of_day_recognition')",
            name="ck_activity_email_template_type",
        ),
        sa.CheckConstraint(
            "length(btrim(subject)) > 0 AND length(subject) <= 200 "
            "AND position(chr(10) in subject) = 0 AND position(chr(13) in subject) = 0",
            name="ck_activity_email_template_subject",
        ),
        sa.CheckConstraint(
            "length(btrim(body)) > 0 AND length(body) <= 5000",
            name="ck_activity_email_template_body",
        ),
    )
    op.create_table(
        "activity_email_preference",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("midday_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("end_of_day_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "user_id", name="uq_activity_email_preference_company_user"),
        sa.ForeignKeyConstraint(
            ["user_id", "company_id"],
            ["user_company.user_id", "user_company.company_id"],
            name="fk_activity_email_preference_membership",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_activity_email_preference_user_id", "activity_email_preference", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_activity_email_preference_user_id", table_name="activity_email_preference")
    op.drop_table("activity_email_preference")
    op.drop_table("activity_email_template")
