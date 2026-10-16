"""Reportes estratégicos de actividad para mandos (RTE-MAIL-UNIFIED-01 V1.2, CP2).

Revision ID: 0023_strategic_reports
Revises: 0022_mail_test_send
Create Date: 2026-10-16

Qué cambia
----------
* `activity_email_template.template_type` admite dos tipos más:
  `strategic_midday_report` y `strategic_end_of_day_report` (CHECK).
* `activity_email_preference` gana `strategic_midday_enabled` y
  `strategic_end_of_day_enabled`, **apagados** (`DEFAULT false`).

Datos existentes: se conservan tal cual. Las plantillas motivacionales y sus
textos no se tocan; las filas de preferencia existentes reciben los dos
interruptores nuevos en `false`, así que **nadie queda suscrito** a un reporte.

La bajada
---------
Borra las plantillas estratégicas personalizadas (si las hay), restaura el CHECK
anterior y quita las dos columnas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_strategic_reports"
down_revision = "0022_mail_test_send"
branch_labels = None
depends_on = None

_TIPOS_V1 = "'midday_motivation', 'end_of_day_recognition'"
_TIPOS_V2 = _TIPOS_V1 + ", 'strategic_midday_report', 'strategic_end_of_day_report'"


def upgrade() -> None:
    op.drop_constraint("ck_activity_email_template_type", "activity_email_template", type_="check")
    op.create_check_constraint(
        "ck_activity_email_template_type", "activity_email_template", f"template_type IN ({_TIPOS_V2})"
    )
    op.add_column(
        "activity_email_preference",
        sa.Column("strategic_midday_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "activity_email_preference",
        sa.Column("strategic_end_of_day_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("activity_email_preference", "strategic_end_of_day_enabled")
    op.drop_column("activity_email_preference", "strategic_midday_enabled")
    op.execute(
        "DELETE FROM activity_email_template "
        "WHERE template_type IN ('strategic_midday_report', 'strategic_end_of_day_report')"
    )
    op.drop_constraint("ck_activity_email_template_type", "activity_email_template", type_="check")
    op.create_check_constraint(
        "ck_activity_email_template_type", "activity_email_template", f"template_type IN ({_TIPOS_V1})"
    )
