"""add index on readings reading_ts

Revision ID: a742ff695c52
Revises: 0c523d2b3998
Create Date: 2026-10-05 15:12:13.131838

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a742ff695c52'
down_revision: Union[str, Sequence[str], None] = '0c523d2b3998'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_readings_reading_ts", "readings", ["reading_ts"])



def downgrade() -> None:
    op.drop_index("ix_readings_reading_ts", table_name="readings")

