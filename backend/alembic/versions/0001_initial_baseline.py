"""initial baseline migration

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-09-07 05:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 01: Baseline migration establishing schema tracking without domain entities.
    pass


def downgrade() -> None:
    pass
