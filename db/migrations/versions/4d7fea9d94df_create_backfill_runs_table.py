"""Create backfill_runs table

Revision ID: 4d7fea9d94df
Revises: d38d230ab69b
Create Date: 2026-10-08 16:05:48.053216

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d7fea9d94df'
down_revision: Union[str, Sequence[str], None] = 'd38d230ab69b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfill_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("batch_id", sa.String, nullable=False),
        sa.Column("meter_id", sa.Integer, nullable=False),
        sa.Column("chunk_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chunk_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rows_read", sa.Integer),
        sa.Column("rows_upserted", sa.Integer),
        sa.Column("rows_rejected", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')", name="status"
        ),
        sa.UniqueConstraint("meter_id", "chunk_start", "chunk_end"),
    )


def downgrade() -> None:
    op.drop_table("backfill_runs")
