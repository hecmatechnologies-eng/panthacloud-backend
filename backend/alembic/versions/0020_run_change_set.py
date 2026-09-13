"""record the change set a run committed

Revision ID: 0020_run_change_set
Revises: 0019_framework_skill_id
Create Date: 2026-09-13 05:00:00.000000

C12: the generated change set is stored on the run so the Studio serves exactly what the pull
request contained, rather than re-deriving it from the current configuration (`CLAUDE.md` §3.7).

Nullable by design: existing runs recorded no change set (NULL means "none"), so there is no
backfill and no seed module.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_run_change_set"
down_revision: str | None = "0019_framework_skill_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integration_runs",
        sa.Column("change_set", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("integration_runs") as batch_op:
        batch_op.drop_column("change_set")
