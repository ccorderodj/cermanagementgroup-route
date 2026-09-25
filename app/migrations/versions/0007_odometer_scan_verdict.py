"""El veredicto del análisis de malware sobre la foto de odómetro (RTE04, §8).

Revision ID: 0007_odometer_scan_verdict
Revises: 0006_odometer_evidence
Create Date: 2026-09-25

Por qué tres columnas y no un booleano
---------------------------------------
"Limpia / no limpia" no puede representar lo que de verdad ocurre. Hay cuatro
respuestas y dos de ellas **no dicen nada del archivo**: `not_configured` es
"este despliegue no tiene escáner" y `unavailable` es "el escáner no contestó".
Colapsarlas en `false` haría pensar que la foto es sospechosa; colapsarlas en
`true` afirmaría un control que nadie ejecutó. Se guardan las cuatro.

`rejected` existe en el CHECK por completitud del dominio, pero **no aparecerá
en ninguna fila con `storage_key`**: una foto que el escáner rechaza no se
almacena, el supervisor hace otra.

Interpretación de los datos existentes
---------------------------------------
Las filas anteriores a esta migración se quedan en `not_configured`, que es la
verdad: se subieron antes de que hubiera análisis, así que nadie las miró.
**No** se marcan limpias. El valor por defecto del servidor lo hace explícito en
vez de dejarlas nulas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_odometer_scan_verdict'
down_revision: Union[str, None] = '0006_odometer_evidence'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('odometer_evidence', sa.Column('scan_status', sa.String(length=20), server_default='not_configured', nullable=False))
    op.add_column('odometer_evidence', sa.Column('scan_provider', sa.String(length=40), nullable=True))
    op.add_column('odometer_evidence', sa.Column('scan_detail', sa.String(length=500), nullable=True))
    # La lista cerrada la garantiza la base: una comprobación en Python protege
    # mientras nadie olvide llamarla; una restricción protege siempre.
    op.create_check_constraint(
        'ck_odometer_scan_status',
        'odometer_evidence',
        "scan_status IN ('clean', 'rejected', 'not_configured', 'unavailable')",
    )


def downgrade() -> None:
    """Reversible: se pierde el veredicto, no ninguna evidencia."""
    op.drop_constraint('ck_odometer_scan_status', 'odometer_evidence', type_='check')
    op.drop_column('odometer_evidence', 'scan_detail')
    op.drop_column('odometer_evidence', 'scan_provider')
    op.drop_column('odometer_evidence', 'scan_status')
