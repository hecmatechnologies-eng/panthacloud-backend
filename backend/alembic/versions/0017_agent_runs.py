"""agent runs and tool calls

Revision ID: 0017_agent_runs
Revises: 0016_retire_contract_layers
Create Date: 2026-09-13 01:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_agent_runs"
down_revision: str | None = "0016_retire_contract_layers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

agent_run_status = sa.Enum(
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
    name="agent_run_status",
)
agent_failure_class = sa.Enum(
    "RETRYABLE", "TERMINAL", "NEEDS_HUMAN", "REFUSED",
    name="agent_failure_class",
)


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("agent_version", sa.String(length=50), nullable=False),
        sa.Column("status", agent_run_status, server_default="PENDING", nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("model_id", sa.String(length=100), nullable=True),
        sa.Column("model_version_reported", sa.String(length=100), nullable=True),
        sa.Column("skill_versions", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("budget", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=14, scale=6), server_default="0", nullable=False),
        sa.Column("execution_context", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("failure_class", agent_failure_class, nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_project_id"), "agent_runs", ["project_id"], unique=False)
    op.create_index(
        "ix_agent_runs_org_created", "agent_runs", ["organization_id", "created_at"], unique=False
    )

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("arguments", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", "sequence", name="uq_agent_tool_call_run_sequence"),
    )
    op.create_index(
        op.f("ix_agent_tool_calls_agent_run_id"),
        "agent_tool_calls",
        ["agent_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_tool_calls_agent_run_id"), table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")

    op.drop_index("ix_agent_runs_org_created", table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_project_id"), table_name="agent_runs")
    op.drop_table("agent_runs")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        agent_failure_class.drop(bind, checkfirst=True)
        agent_run_status.drop(bind, checkfirst=True)
