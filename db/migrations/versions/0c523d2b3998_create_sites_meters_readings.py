"""create sites meters readings

Revision ID: 0c523d2b3998
Revises: 
Create Date: 2026-10-05 14:49:17.856192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c523d2b3998'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("region", sa.String),
    )
    op.create_table(
        "meters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_id", sa.Integer, sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("meter_type", sa.String, nullable=False),
        sa.Column("install_date", sa.Date),
    )
    op.create_table(
        "readings",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("meter_id", sa.Integer, sa.ForeignKey("meters.id"), nullable=False),
        sa.Column("reading_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kwh_value", sa.Numeric(10, 3)),
        sa.Column("status", sa.String, nullable=False, server_default="ok"),
        sa.UniqueConstraint("meter_id", "reading_ts"),
    )



def downgrade() -> None:
    op.drop_table("readings")
    op.drop_table("meters")
    op.drop_table("sites")

