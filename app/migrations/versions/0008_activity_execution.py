"""El bloque de ejecución de actividad tras la llegada (RTE05-C1).

Revision ID: 0008_activity_execution
Revises: 0007_odometer_scan_verdict
Create Date: 2026-09-28

Dos tablas y una idea
----------------------
`activity_execution` es la parada: un inicio, un fin, una duración, un resultado
y una nota. `activity_execution_activity` son las etiquetas de esa parada —de una
a varias— sin horas ni estado propios.

Es la decisión PD-01 llevada al esquema. Modelarlo con un cronómetro por
actividad habría obligado a inventar horas de inicio que nadie midió: quien
atiende a un cliente hace tres cosas en la misma visita, no tres visitas.

Las restricciones que importan
-------------------------------
* `uq_activity_execution_trip` — **uno por viaje**. Reintentar el arranque o
  pulsarlo desde dos dispositivos no crea un segundo bloque.
* `ck_activity_execution_terminal_facts` — terminar exige hora **y** resultado.
  Un bloque terminal sin resultado sería el hecho fabricado que las instrucciones
  prohíben, y aquí no puede existir.
* Claves foráneas compuestas con `company_id` — referenciar el viaje, la jornada
  o un valor de otro tenant es imposible por construcción, no por cuidado.
* `RESTRICT` sobre `standard_value` — el valor configurado puede desactivarse o
  retirarse como lápida, pero no desaparecer de debajo de un histórico.

Índices revisados a mano
-------------------------
El autogenerate propuso tres índices que ya estaban: uno sobre `trip_id`, que
`uq_activity_execution_trip` indexa por ser único, y dos idénticos sobre
`activity_execution_id`, cubierto por la columna inicial de
`uq_activity_execution_value`. Se quitaron: un índice duplicado no protege nada
y encarece cada escritura.

Nada que interpretar
--------------------
No toca ninguna fila existente. Los viajes `ARRIVED` anteriores a RTE05 se quedan
exactamente como están: la integridad histórica prohíbe fabricarles una ejecución,
y esta migración no lo hace.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_activity_execution'
down_revision: Union[str, None] = '0007_odometer_scan_verdict'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('activity_execution',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('work_session_id', sa.Integer(), nullable=False),
    sa.Column('trip_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='in_progress', nullable=False),
    sa.Column('terminal_action', sa.String(length=10), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at_source', sa.String(length=20), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at_source', sa.String(length=20), nullable=True),
    sa.Column('outcome_standard_value_id', sa.Integer(), nullable=True),
    sa.Column('outcome_label', sa.String(length=120), nullable=True),
    sa.Column('received_by_standard_value_id', sa.Integer(), nullable=True),
    sa.Column('received_by_label', sa.String(length=120), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("(status = 'in_progress' AND ended_at IS NULL AND terminal_action IS NULL AND outcome_standard_value_id IS NULL) OR (status IN ('completed', 'left') AND ended_at IS NOT NULL AND terminal_action IS NOT NULL AND outcome_standard_value_id IS NOT NULL)", name='ck_activity_execution_terminal_facts'),
    sa.CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='ck_activity_execution_ends_after_start'),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trip_id', 'company_id'], ['trip.id', 'trip.company_id'], name='fk_activity_execution_trip_same_company', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['work_session_id', 'company_id'], ['work_session.id', 'work_session.company_id'], name='fk_activity_execution_session_same_company', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'company_id', name='uq_activity_execution_id_company'),
    sa.UniqueConstraint('trip_id', name='uq_activity_execution_trip')
    )
    op.create_index(op.f('ix_activity_execution_company_id'), 'activity_execution', ['company_id'], unique=False)
    op.create_index(op.f('ix_activity_execution_id'), 'activity_execution', ['id'], unique=False)
    op.create_index('ix_activity_execution_session', 'activity_execution', ['company_id', 'work_session_id'], unique=False)
    op.create_index(op.f('ix_activity_execution_work_session_id'), 'activity_execution', ['work_session_id'], unique=False)
    op.create_table('activity_execution_activity',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('activity_execution_id', sa.Integer(), nullable=False),
    sa.Column('standard_value_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['activity_execution_id', 'company_id'], ['activity_execution.id', 'activity_execution.company_id'], name='fk_activity_value_execution_same_company', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['standard_value_id', 'company_id'], ['standard_value.id', 'standard_value.company_id'], name='fk_activity_value_standard_same_company', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_execution_id', 'standard_value_id', name='uq_activity_execution_value')
    )
    op.create_index(op.f('ix_activity_execution_activity_company_id'), 'activity_execution_activity', ['company_id'], unique=False)
    op.create_index(op.f('ix_activity_execution_activity_id'), 'activity_execution_activity', ['id'], unique=False)


def downgrade() -> None:
    """Reversible: se pierden los bloques de ejecución, nada más."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_activity_execution_activity_id'), table_name='activity_execution_activity')
    op.drop_index(op.f('ix_activity_execution_activity_company_id'), table_name='activity_execution_activity')
    op.drop_table('activity_execution_activity')
    op.drop_index(op.f('ix_activity_execution_work_session_id'), table_name='activity_execution')
    op.drop_index('ix_activity_execution_session', table_name='activity_execution')
    op.drop_index(op.f('ix_activity_execution_id'), table_name='activity_execution')
    op.drop_index(op.f('ix_activity_execution_company_id'), table_name='activity_execution')
    op.drop_table('activity_execution')
