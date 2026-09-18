"""website analyses

Revision ID: 0018_website_analyses
Revises: 0017_agent_runs
Create Date: 2026-09-13 02:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_website_analyses"
down_revision: str | None = "0017_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "website_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("framework_skill_id", sa.String(length=100), nullable=True),
        sa.Column("router", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("package_manager", sa.String(length=50), nullable=True),
        sa.Column("build_command", sa.String(length=255), nullable=True),
        sa.Column("entry_points", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("integration_candidates", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("design_tokens", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("protected_paths", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("unsupported_reason", sa.Text(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["website_integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_website_analyses_integration_created",
        "website_analyses",
        ["integration_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_website_analyses_integration_created", table_name="website_analyses")
    op.drop_table("website_analyses")
