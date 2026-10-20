"""Zona operativa de la compañía (RTE-MAIL-CLOSE-01).

Revision ID: 0026_company_time_zone
Revises: 0025_activity_email_resend
Create Date: 2026-10-20

Qué añade
---------
`company.operational_time_zone`: la zona IANA de referencia del tenant. Los
correos de actividad la usan cuando el destinatario no tiene zona propia (un
administrador que representa al CEO no inicia jornadas). Vacía por defecto: el
correo queda en `configuration_required` hasta que alguien la fije en el
perfil de la compañía. No se rellena ninguna: elegir la zona de una compañía
es una decisión de negocio, no algo que una migración pueda deducir.

La validez del nombre IANA la comprueba la API (`zoneinfo`); la base sólo
limita la longitud.

La bajada
---------
Borra la columna.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_company_time_zone"
down_revision = "0025_activity_email_resend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company", sa.Column("operational_time_zone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("company", "operational_time_zone")
