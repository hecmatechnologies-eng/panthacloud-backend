"""discovery runs

Revision ID: 0006_discovery
Revises: 0005_snapshots
Create Date: 2026-09-08 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_discovery"
down_revision: str | None = "0005_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

discovery_status = sa.Enum(
    "PENDING", "RUNNING", "COMPLETED", "FAILED",
    name="discovery_status"
)


def upgrade() -> None:
    op.create_table(
        "discovery_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("status", discovery_status, server_default="PENDING", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_discovery_runs_snapshot_id"), "discovery_runs", ["snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_discovery_runs_snapshot_id"), table_name="discovery_runs")
    op.drop_table("discovery_runs")
    discovery_status.drop(op.get_bind(), checkfirst=True)
