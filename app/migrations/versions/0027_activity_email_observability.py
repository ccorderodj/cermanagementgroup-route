"""Observabilidad del envío de correos de actividad (RTE-MAIL-CLOSE-01, CP2).

Revision ID: 0027_activity_email_obs
Revises: 0026_company_time_zone
Create Date: 2026-10-20

Qué añade
---------
* `activity_email_dispatch_run`: la **última** pasada de cada reloj del envío
  automático (`schedule`, el programador interno; `reconcile`, el Scheduled Job
  de DigitalOcean). Una fila por origen, sobrescrita: es un latido para que la
  pantalla diga cuándo corrió cada uno, no un historial. Sólo contadores.
* `activity_email_delivery.time_zone`: la zona con que se calcularon el corte
  y el vencimiento, para que el historial la enseñe.

Interpretación de los datos existentes: las entregas anteriores quedan con
`time_zone` vacío. No se rellena: la zona de entonces no se puede deducir con
certeza de la de hoy (el destinatario pudo cambiar de zona).

La bajada
---------
Borra la tabla y la columna.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_activity_email_obs"
down_revision = "0026_company_time_zone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_email_dispatch_run",
        sa.Column("source", sa.String(20), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("source IN ('schedule', 'reconcile')", name="ck_activity_email_dispatch_run_source"),
        sa.CheckConstraint("outcome IN ('completed', 'failed')", name="ck_activity_email_dispatch_run_outcome"),
    )
    op.add_column("activity_email_delivery", sa.Column("time_zone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("activity_email_delivery", "time_zone")
    op.drop_table("activity_email_dispatch_run")
