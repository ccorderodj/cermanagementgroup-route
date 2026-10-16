"""RTE09: estado operativo, snapshots de combustible y referencia de precios.

Revision ID: 0016_rte09_reports_fuel
Revises: 0015_time_zone_sources
Create Date: 2026-10-12

Qué añade
---------
* `supervisor_profile.operational_state` — el estado cuyo precio aplica a las
  jornadas del supervisor (D-1). Lo fija un administrador; nace vacío.
* `work_session.operational_state_snapshot` y `work_session.fuel_grade_snapshot`
  — lo que se congela al empezar la jornada, junto al MPG que ya se congelaba.
* `fuel_reference` — la historia de precios, **append-only**.
* `work_session_fuel_estimate` — la estimación final de cada jornada con su
  procedencia, **append-only**.

Todo es aditivo: columnas `NULL`, tablas nuevas. Ningún dato existente cambia
de significado.

Datos existentes: el grado de combustible
-----------------------------------------
Las jornadas anteriores tienen congelado el **vehículo** (`vehicle_id`) pero no
su grado. El grado actual de ese vehículo no basta: si alguien lo editó
después de la jornada, el actual no es el que tenía entonces.

Por eso el relleno lee la **auditoría** del vehículo. Para cada jornada:

1. si hay un cambio de `fuel_grade` del vehículo **posterior** al inicio de la
   jornada, el grado de entonces es el `old` del **primero** de esos cambios;
2. si no lo hay, el grado no cambió desde entonces y el actual es el correcto.

Es exacto mientras la auditoría esté completa, que es lo que garantiza su
disparador append-only. Las jornadas sin vehículo quedan sin grado, que es la
verdad: no hubo vehículo.

Datos existentes: el estado operativo
-------------------------------------
**No se rellena.** El concepto no existía cuando esas jornadas empezaron, y
deducirlo hoy del supervisor sería exactamente lo que D-1 prohíbe: calcular
la historia con un dato actual. Esas jornadas quedan sin estado y su coste
estimado no se resuelve —visible como `0`, con su motivo en el API—.

La bajada
---------
Elimina tablas y columnas. Se pierde lo capturado desde la subida —estados,
snapshots, precios y estimaciones—, que es exactamente lo que esta migración
añadió. `fuel_reference` y `work_session_fuel_estimate` son append-only, pero
`DROP TABLE` no pasa por sus disparadores de fila.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_rte09_reports_fuel"
down_revision = "0015_time_zone_sources"
branch_labels = None
depends_on = None

#: Tablas con el disparador append-only genérico del esquema. A nivel de módulo
#: porque `test_every_trigger_created_by_a_migration_is_watched` deriva de aquí
#: los nombres que `EXPECTED_TRIGGERS` tiene que vigilar.
APPEND_ONLY_TABLES: tuple[str, ...] = ("fuel_reference", "work_session_fuel_estimate")

GRADOS = "'regular', 'midgrade', 'premium', 'diesel'"

#: El relleno del grado de las jornadas anteriores (ver el docstring). A nivel de
#: módulo para que la prueba de la migración ejecute **este** SQL y no una copia.
RELLENO_GRADO_SQL = """
        UPDATE work_session AS ws
        SET fuel_grade_snapshot = COALESCE(
            (
                SELECT ae.changes -> 'fuel_grade' ->> 'old'
                FROM audit_event AS ae
                WHERE ae.company_id = ws.company_id
                  AND ae.entity_type = 'vehicle'
                  AND ae.entity_id = ws.vehicle_id
                  AND ae.action = 'update'
                  AND ae.changes ? 'fuel_grade'
                  AND ae.occurred_at > ws.started_at
                ORDER BY ae.occurred_at ASC, ae.id ASC
                LIMIT 1
            ),
            v.fuel_grade
        )
        FROM vehicle AS v
        WHERE v.id = ws.vehicle_id
          AND v.company_id = ws.company_id
          AND ws.fuel_grade_snapshot IS NULL
        """


def upgrade() -> None:
    op.add_column(
        "supervisor_profile",
        sa.Column("operational_state", sa.String(length=2), nullable=True),
    )
    op.create_check_constraint(
        "ck_supervisor_profile_operational_state",
        "supervisor_profile",
        "operational_state IS NULL OR operational_state ~ '^[A-Z]{2}$'",
    )

    op.add_column(
        "work_session",
        sa.Column("operational_state_snapshot", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "work_session",
        sa.Column("fuel_grade_snapshot", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_work_session_operational_state_snapshot",
        "work_session",
        "operational_state_snapshot IS NULL OR operational_state_snapshot ~ '^[A-Z]{2}$'",
    )
    op.create_check_constraint(
        "ck_work_session_fuel_grade_snapshot",
        "work_session",
        f"fuel_grade_snapshot IS NULL OR fuel_grade_snapshot IN ({GRADOS})",
    )

    op.create_table(
        "fuel_reference",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("fuel_grade", sa.String(length=20), nullable=False),
        sa.Column("price_per_gallon", sa.Numeric(8, 4), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column(
            "loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"fuel_grade IN ({GRADOS})", name="ck_fuel_reference_fuel_grade"),
        sa.CheckConstraint("state_code ~ '^[A-Z]{2}$'", name="ck_fuel_reference_state_code"),
        sa.CheckConstraint("price_per_gallon > 0", name="ck_fuel_reference_price_positive"),
        sa.CheckConstraint("length(trim(source)) > 0", name="ck_fuel_reference_source"),
    )
    op.create_index(
        "ix_fuel_reference_lookup",
        "fuel_reference",
        ["company_id", "state_code", "fuel_grade", "effective_date"],
    )

    op.create_table(
        "work_session_fuel_estimate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("work_session_id", sa.Integer(), nullable=False),
        sa.Column("fuel_reference_id", sa.Integer(), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("fuel_grade", sa.String(length=20), nullable=False),
        sa.Column("operational_mpg", sa.Numeric(5, 2), nullable=False),
        sa.Column("official_miles", sa.Numeric(12, 4), nullable=False),
        sa.Column("price_per_gallon", sa.Numeric(8, 4), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("estimated_gallons", sa.Numeric(12, 4), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_session_id", "company_id"],
            ["work_session.id", "work_session.company_id"],
            name="fk_fuel_estimate_session_same_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fuel_reference_id"], ["fuel_reference.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_session_id", name="uq_work_session_fuel_estimate_session"),
        sa.CheckConstraint(f"fuel_grade IN ({GRADOS})", name="ck_fuel_estimate_fuel_grade"),
        sa.CheckConstraint("operational_mpg > 0", name="ck_fuel_estimate_mpg_positive"),
        sa.CheckConstraint("price_per_gallon > 0", name="ck_fuel_estimate_price_positive"),
        sa.CheckConstraint(
            "official_miles >= 0 AND estimated_gallons >= 0 AND estimated_cost >= 0",
            name="ck_fuel_estimate_non_negative",
        ),
    )

    # Hechos observados y resultados finales: se añaden, no se corrigen.
    for tabla in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {tabla}_is_append_only()
            RETURNS trigger AS $BODY$
            BEGIN
                RAISE EXCEPTION '{tabla} is append-only: % is not allowed', TG_OP;
            END;
            $BODY$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{tabla}_append_only
            BEFORE UPDATE OR DELETE ON {tabla}
            FOR EACH ROW EXECUTE FUNCTION {tabla}_is_append_only();
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{tabla}_no_truncate
            BEFORE TRUNCATE ON {tabla}
            FOR EACH STATEMENT EXECUTE FUNCTION {tabla}_is_append_only();
            """
        )

    # El grado de entonces, reconstruido con la auditoría del vehículo (ver el
    # docstring). Sólo las jornadas con vehículo congelado.
    op.execute(RELLENO_GRADO_SQL)


def downgrade() -> None:
    op.drop_table("work_session_fuel_estimate")
    op.drop_index("ix_fuel_reference_lookup", table_name="fuel_reference")
    op.drop_table("fuel_reference")
    for tabla in APPEND_ONLY_TABLES:
        op.execute(f"DROP FUNCTION IF EXISTS {tabla}_is_append_only()")
    op.drop_constraint("ck_work_session_fuel_grade_snapshot", "work_session", type_="check")
    op.drop_constraint(
        "ck_work_session_operational_state_snapshot", "work_session", type_="check"
    )
    op.drop_column("work_session", "fuel_grade_snapshot")
    op.drop_column("work_session", "operational_state_snapshot")
    op.drop_constraint(
        "ck_supervisor_profile_operational_state", "supervisor_profile", type_="check"
    )
    op.drop_column("supervisor_profile", "operational_state")
