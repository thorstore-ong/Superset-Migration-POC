"""deliberately broken migration

Revision ID: c029f09372b9
Revises: 4d7fea9d94df
Create Date: 2026-10-20 16:48:49.342164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c029f09372b9'
down_revision: Union[str, Sequence[str], None] = '4d7fea9d94df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
     op.execute("ALTER TABLE readings ADD COLUMN broken")


def downgrade() -> None:
    """Downgrade schema."""
    pass
