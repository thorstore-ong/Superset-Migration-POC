"""create readings_staging table

Revision ID: d38d230ab69b
Revises: fa9ba952062e
Create Date: 2026-10-07 10:46:12.741006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd38d230ab69b'
down_revision: Union[str, Sequence[str], None] = 'fa9ba952062e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "readings_staging",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("batch_id", sa.String, nullable=False),
        sa.Column("meter_id", sa.Text),       # everything TEXT —
        sa.Column("reading_ts", sa.Text),     # nothing here is allowed
        sa.Column("kwh_value", sa.Text),      # to fail to insert
        sa.Column("status", sa.Text),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    
    )


def downgrade() -> None:
   op.drop_table("readings_staging")
