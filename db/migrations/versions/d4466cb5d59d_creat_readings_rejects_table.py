"""creat readings_rejects table

Revision ID: d4466cb5d59d
Revises: b899220cfc3c
Create Date: 2026-10-05 16:51:05.044240

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4466cb5d59d'
down_revision: Union[str, Sequence[str], None] = 'ddcb7e043cd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Types are not strict due to the fact that these are rejected readings, that may have broken data, 
# and we want to capture that data as is, without any type constraints. 
def upgrade() -> None:
    op.create_table(
        "readings_rejects",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("meter_id", sa.Integer()),
        sa.Column("reading_ts", sa.DateTime(timezone=True)),
        sa.Column("raw_kwh_value", sa.Text),
        sa.Column("status", sa.String),
        sa.Column("reason", sa.String, nullable=False),
        sa.Column("rejected_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("readings_rejects")
