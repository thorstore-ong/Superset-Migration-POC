"""make normalized_kw not null (contract)

Revision ID: b899220cfc3c
Revises: bece91a92dee
Create Date: 2026-10-05 16:29:53.365524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b899220cfc3c'
down_revision: Union[str, Sequence[str], None] = 'bece91a92dee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
   op.alter_column("readings", "normalized_kwh", nullable=False)


def downgrade() -> None:
    op.alter_column("readings", "normalized_kwh", nullable=True)
