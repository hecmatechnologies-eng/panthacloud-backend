"""integration adapters and execution plans

Revision ID: 0008_integration_adapters
Revises: 0007_contracts
Create Date: 2026-09-08 17:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_integration_adapters"
down_revision: str | None = "0007_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

adapter_status = sa.Enum(
    "PENDING", "PLANNED", "REVIEW_REQUIRED", "BLOCKED", "READY", "FAILED",
    name="adapter_status",
)

adapter_type = sa.Enum(
    "DATABASE", "CACHE", "PAYMENT", "STORAGE", "HTTP_API", "WEBHOOK",
    "VERSION_CONTROL", "AUTHENTICATION", "MESSAGE_BROKER", "UNKNOWN",
    name="adapter_type",
)

execution_plan_status = sa.Enum(
    "DRAFT", "PLANNED", "REVIEW_REQUIRED", "BLOCKED", "READY", "FAILED",
    name="execution_plan_status",
)


def upgrade() -> None:
    # 1. Create integration_adapters table
    op.create_table(
        "integration_adapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_plan_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("adapter_type", adapter_type, nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("status", adapter_status, server_default="PLANNED", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("configuration", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("required_credentials", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("operations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("prerequisites", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("constraints", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_plan_id"], ["integration_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_integration_adapters_integration_plan_id"), "integration_adapters", ["integration_plan_id"], unique=False)
    op.create_index(op.f("ix_integration_adapters_snapshot_id"), "integration_adapters", ["snapshot_id"], unique=False)

    # 2. Create execution_plans table
    op.create_table(
        "execution_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("integration_plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", execution_plan_status, server_default="PLANNED", nullable=False),
        sa.Column("steps", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("required_credentials", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("prerequisites", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("approval_requirements", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("blocked_reasons", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["integration_plan_id"], ["integration_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_execution_plans_project_id"), "execution_plans", ["project_id"], unique=False)
    op.create_index(op.f("ix_execution_plans_snapshot_id"), "execution_plans", ["snapshot_id"], unique=False)
    op.create_index(op.f("ix_execution_plans_integration_plan_id"), "execution_plans", ["integration_plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_execution_plans_integration_plan_id"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_snapshot_id"), table_name="execution_plans")
    op.drop_index(op.f("ix_execution_plans_project_id"), table_name="execution_plans")
    op.drop_table("execution_plans")

    op.drop_index(op.f("ix_integration_adapters_snapshot_id"), table_name="integration_adapters")
    op.drop_index(op.f("ix_integration_adapters_integration_plan_id"), table_name="integration_adapters")
    op.drop_table("integration_adapters")
