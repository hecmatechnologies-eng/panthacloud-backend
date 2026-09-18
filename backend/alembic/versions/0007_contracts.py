"""contracts and integration plans

Revision ID: 0007_contracts
Revises: 0006_discovery
Create Date: 2026-09-08 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_contracts"
down_revision: str | None = "0006_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

contract_status = sa.Enum(
    "PENDING", "RUNNING", "COMPLETED", "FAILED",
    name="contract_status",
)

contract_source = sa.Enum(
    "OPENAPI", "SWAGGER", "STATIC_ROUTE", "DISCOVERY",
    name="contract_source",
)

integration_plan_status = sa.Enum(
    "PENDING", "READY", "REVIEW_REQUIRED", "BLOCKED", "COMPLETED", "FAILED",
    name="integration_plan_status",
)


def upgrade() -> None:
    # 1. Create api_contracts table
    op.create_table(
        "api_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", contract_status, server_default="PENDING", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), server_default="1.0.0", nullable=False),
        sa.Column("format", sa.String(length=64), nullable=False),
        sa.Column("servers", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("authentication", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("schemas", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("reconciliation", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["discovery_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_contracts_snapshot_id"), "api_contracts", ["snapshot_id"], unique=False)
    op.create_index(op.f("ix_api_contracts_discovery_run_id"), "api_contracts", ["discovery_run_id"], unique=False)

    # 2. Create api_operations table
    op.create_table(
        "api_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("operation_id", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", contract_source, nullable=False),
        sa.Column("source_file", sa.String(length=1024), nullable=True),
        sa.Column("source_line", sa.Integer(), nullable=True),
        sa.Column("authentication_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("request_schema", sa.JSON(), nullable=True),
        sa.Column("response_schema", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["api_contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_operations_contract_id"), "api_operations", ["contract_id"], unique=False)

    # 3. Create integration_plans table
    op.create_table(
        "integration_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("status", integration_plan_status, server_default="PENDING", nullable=False),
        sa.Column("candidates", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("required_credentials", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["api_contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_integration_plans_project_id"), "integration_plans", ["project_id"], unique=False)
    op.create_index(op.f("ix_integration_plans_snapshot_id"), "integration_plans", ["snapshot_id"], unique=False)
    op.create_index(op.f("ix_integration_plans_contract_id"), "integration_plans", ["contract_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_plans_contract_id"), table_name="integration_plans")
    op.drop_index(op.f("ix_integration_plans_snapshot_id"), table_name="integration_plans")
    op.drop_index(op.f("ix_integration_plans_project_id"), table_name="integration_plans")
    op.drop_table("integration_plans")

    op.drop_index(op.f("ix_api_operations_contract_id"), table_name="api_operations")
    op.drop_table("api_operations")

    op.drop_index(op.f("ix_api_contracts_discovery_run_id"), table_name="api_contracts")
    op.drop_index(op.f("ix_api_contracts_snapshot_id"), table_name="api_contracts")
    op.drop_table("api_contracts")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        integration_plan_status.drop(bind, checkfirst=True)
        contract_source.drop(bind, checkfirst=True)
        contract_status.drop(bind, checkfirst=True)
