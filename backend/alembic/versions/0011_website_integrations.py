"""website integrations and integration runs

Revision ID: 0011_website_integrations
Revises: 0010_assistant
Create Date: 2026-09-08 22:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_website_integrations"
down_revision: str | None = "0010_assistant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

website_integration_status = sa.Enum(
    "NOT_CONNECTED",
    "CONNECTED",
    "PLANNING",
    "SANDBOX_READY",
    "GENERATING",
    "VALIDATING",
    "READY_FOR_PR",
    "PR_CREATED",
    "FAILED",
    name="website_integration_status",
)

integration_run_status = sa.Enum(
    "PENDING",
    "RUNNING",
    "VALIDATING",
    "READY_FOR_PR",
    "PR_CREATED",
    "FAILED",
    "CANCELLED",
    name="integration_run_status",
)

website_framework = sa.Enum(
    "REACT_NEXTJS",
    "GENERIC_HTML",
    name="website_framework",
)


def upgrade() -> None:
    op.create_table(
        "website_integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), server_default="github", nullable=False),
        sa.Column("repository_owner", sa.String(length=255), nullable=False),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=100), server_default="main", nullable=False),
        sa.Column("integration_branch", sa.String(length=150), nullable=True),
        sa.Column("framework", website_framework, server_default="REACT_NEXTJS", nullable=False),
        sa.Column("website_root_dir", sa.String(length=255), server_default="/", nullable=False),
        sa.Column("widget_target_path", sa.String(length=255), server_default="app/layout.tsx", nullable=False),
        sa.Column("status", website_integration_status, server_default="NOT_CONNECTED", nullable=False),
        sa.Column("encrypted_secrets", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_website_integration_project_id"),
    )
    op.create_index(
        op.f("ix_website_integrations_project_id"),
        "website_integrations",
        ["project_id"],
        unique=True,
    )

    op.create_table(
        "integration_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("status", integration_run_status, server_default="PENDING", nullable=False),
        sa.Column("branch_name", sa.String(length=200), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("pull_request_number", sa.Integer(), nullable=True),
        sa.Column("pull_request_url", sa.String(length=512), nullable=True),
        sa.Column("sandbox_ref", sa.String(length=100), nullable=False),
        sa.Column("plan_summary", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("generated_files_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("modified_files_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["website_integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_integration_runs_integration_id"),
        "integration_runs",
        ["integration_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_runs_integration_id"), table_name="integration_runs")
    op.drop_table("integration_runs")
    op.drop_index(op.f("ix_website_integrations_project_id"), table_name="website_integrations")
    op.drop_table("website_integrations")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        integration_run_status.drop(bind, checkfirst=True)
        website_framework.drop(bind, checkfirst=True)
        website_integration_status.drop(bind, checkfirst=True)
