"""enforce kwh_value nonneg with reject routing

Revision ID: fa9ba952062e
Revises: b899220cfc3c
Create Date: 2026-10-06 14:46:40.549621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa9ba952062e'
down_revision: Union[str, Sequence[str], None] = 'b899220cfc3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
       INSERT INTO readings_rejects (meter_id, reading_ts, raw_kwh_value, status, reason)
       SELECT meter_id, reading_ts, kwh_value::text, status, 'invalid_kwh_value'
       FROM readings
       WHERE kwh_value < 0
       """)

    op.execute("DELETE FROM readings WHERE kwh_value < 0")

    op.create_check_constraint(
        "ck_readings_kwh_nonneg", "readings", "kwh_value >= 0"
    )



def downgrade() -> None:
    op.drop_constraint("ck_readings_kwh_nonneg", "readings", type_="check")

    op.execute("""
       INSERT INTO readings (meter_id, reading_ts, kwh_value, status, normalized_kwh)
       SELECT meter_id, reading_ts, raw_kwh_value::numeric, status, NULL
       FROM readings_rejects WHERE reason = 'invalid_kwh_value'
       """)

    op.execute("DELETE FROM readings_rejects WHERE reason = 'invalid_kwh_value'")
