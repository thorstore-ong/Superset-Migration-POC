"""backfill normalized_kwh with reject routing

Revision ID: bece91a92dee
Revises: ddcb7e043cd6
Create Date: 2026-10-05 16:26:20.353058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bece91a92dee'
down_revision: Union[str, Sequence[str], None] = 'd4466cb5d59d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
       INSERT INTO readings_rejects (meter_id, reading_ts, raw_kwh_value, status, reason)
       SELECT meter_id, reading_ts, kwh_value::text, status, 'cannot_normalize'
       FROM readings
       WHERE kwh_value IS NULL
       """)

    op.execute("DELETE FROM readings WHERE kwh_value IS NULL")

    op.execute("""
       UPDATE readings
       SET normalized_kwh = kwh_value / 1000
       WHERE normalized_kwh IS NULL
    """)


def downgrade() -> None:
    op.execute("""
       INSERT INTO readings (meter_id, reading_ts, kwh_value, status)
       SELECT meter_id, reading_ts, NULL, status
       FROM readings_rejects WHERE reason = 'cannot_normalize'
       """)

    op.execute("DELETE FROM readings_rejects WHERE reason = 'cannot_normalize'")
    op.execute("UPDATE readings SET normalized_kwh = NULL")
