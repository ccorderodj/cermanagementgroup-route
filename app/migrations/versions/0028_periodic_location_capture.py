"""Captura periódica de ubicación (RTE-LOC-02).

Revision ID: 0028_periodic_location_capture
Revises: 0027_activity_email_obs
Create Date: 2026-10-20

Qué añade
---------
* `location_capture_setting`: una fila por compañía cuando alguien la configura.
  Sin fila = **apagada**, 300 s. No se siembra nada: ninguna compañía empieza a
  capturar por migrar.
* `location_sample`: las muestras periódicas, separadas de `location_fix`, que
  no se toca. Idempotencia por `(company_id, client_sample_id)`. Sin particionar:
  una clave única en una tabla particionada tiene que incluir la columna de
  partición, y eso rompería la idempotencia sin la hora (ver el modelo).
* `location_point_timeline`: **vista de sólo lectura** que une los puntos de
  evento (`location_fix`, `source='event'`) y las muestras (`source='periodic'`)
  por compañía y jornada, con el usuario de la jornada.
  - El viaje de un punto de evento sale de su sujeto (`trip_attribution='event'`).
  - El de una muestra, del único viaje de la misma jornada cuyo intervalo
    [salida, llegada o fin) contiene la hora de captura
    (`trip_attribution='interval'`, **provisional**: depende del reloj del
    dispositivo). Si no hay exactamente uno, o el viaje sigue abierto, queda
    sin viaje.

La bajada
---------
Borra la vista y las dos tablas, y con ellas las muestras.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_periodic_location_capture"
down_revision = "0027_activity_email_obs"
branch_labels = None
depends_on = None

_VISTA = """
CREATE VIEW location_point_timeline AS
SELECT
    'event'::text AS source,
    f.id::bigint AS point_id,
    f.company_id,
    f.work_session_id,
    ws.user_id,
    ws.session_date,
    f.event_kind,
    CASE f.subject_kind
        WHEN 'trip' THEN f.subject_id
        WHEN 'trip_purpose_change' THEN tpc.trip_id
        WHEN 'activity_execution' THEN ae.trip_id
    END AS trip_id,
    CASE WHEN f.subject_kind = 'work_session' THEN NULL ELSE 'event' END AS trip_attribution,
    f.latitude,
    f.longitude,
    f.accuracy_m,
    f.device_captured_at AS captured_at,
    f.server_received_at AS received_at
FROM location_fix f
JOIN work_session ws ON ws.id = f.work_session_id AND ws.company_id = f.company_id
LEFT JOIN trip_purpose_change tpc
    ON f.subject_kind = 'trip_purpose_change' AND tpc.id = f.subject_id AND tpc.company_id = f.company_id
LEFT JOIN activity_execution ae
    ON f.subject_kind = 'activity_execution' AND ae.id = f.subject_id AND ae.company_id = f.company_id
UNION ALL
SELECT
    'periodic'::text,
    s.id,
    s.company_id,
    s.work_session_id,
    s.user_id,
    ws.session_date,
    NULL,
    CASE WHEN m.viajes = 1 THEN m.trip_id END,
    CASE WHEN m.viajes = 1 THEN 'interval' END,
    s.latitude,
    s.longitude,
    s.accuracy_m,
    s.device_captured_at,
    s.server_received_at
FROM location_sample s
JOIN work_session ws ON ws.id = s.work_session_id AND ws.company_id = s.company_id
LEFT JOIN LATERAL (
    SELECT count(*) AS viajes, min(t.id) AS trip_id
    FROM trip t
    WHERE t.company_id = s.company_id
      AND t.work_session_id = s.work_session_id
      AND t.started_at <= s.device_captured_at
      AND s.device_captured_at < COALESCE(t.arrived_at, t.ended_at)
) m ON true
"""


def upgrade() -> None:
    op.create_table(
        "location_capture_setting",
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("interval_seconds BETWEEN 60 AND 3600", name="ck_location_capture_setting_interval"),
    )
    op.create_table(
        "location_sample",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_sample_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("accuracy_m", sa.Numeric(10, 2), nullable=False),
        sa.Column("device_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("server_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_seconds_applied", sa.Integer(), nullable=False),
        sa.UniqueConstraint("company_id", "client_sample_id", name="uq_location_sample_client_id"),
        sa.ForeignKeyConstraint(
            ["work_session_id", "company_id"], ["work_session.id", "work_session.company_id"],
            name="fk_location_sample_session_same_company", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_location_sample_coordinates"
        ),
        sa.CheckConstraint("accuracy_m >= 0", name="ck_location_sample_accuracy"),
        sa.CheckConstraint("interval_seconds_applied BETWEEN 60 AND 3600", name="ck_location_sample_interval"),
    )
    op.create_index("ix_location_sample_company_received", "location_sample", ["company_id", "server_received_at"])
    op.create_index(
        "ix_location_sample_session", "location_sample", ["company_id", "work_session_id", "device_captured_at"]
    )
    op.execute(_VISTA)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS location_point_timeline")
    op.drop_index("ix_location_sample_session", table_name="location_sample")
    op.drop_index("ix_location_sample_company_received", table_name="location_sample")
    op.drop_table("location_sample")
    op.drop_table("location_capture_setting")
