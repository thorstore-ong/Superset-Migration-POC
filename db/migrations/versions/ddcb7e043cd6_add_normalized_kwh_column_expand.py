"""add normalized_kwh column (expand)

Revision ID: ddcb7e043cd6
Revises: a742ff695c52
Create Date: 2026-10-05 16:20:09.466978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddcb7e043cd6'
down_revision: Union[str, Sequence[str], None] = 'a742ff695c52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
   op.add_column("readings", sa.Column("normalized_kwh", sa.Numeric(10, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("readings", "normalized_kwh")
