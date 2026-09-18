"""repository snapshots and audit events

Revision ID: 0005_snapshots
Revises: 0004_repositories
Create Date: 2026-09-08 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_snapshots"
down_revision: str | None = "0004_repositories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

snapshot_status = sa.Enum(
    "PENDING", "ACQUIRING", "READY", "FAILED", "EXPIRED", "DELETED",
    name="snapshot_status"
)


def upgrade() -> None:
    # 1. Create repository_snapshots table
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("status", snapshot_status, server_default="PENDING", nullable=False),
        sa.Column("workspace_reference", sa.String(length=255), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_repository_snapshots_repository_id"), "repository_snapshots", ["repository_id"], unique=False)
    op.create_index(op.f("ix_repository_snapshots_commit_sha"), "repository_snapshots", ["commit_sha"], unique=False)

    # 2. Create audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_organization_id"), "audit_events", ["organization_id"], unique=False)
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"], unique=False)
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_events_resource_id"), "audit_events", ["resource_id"], unique=False)


def downgrade() -> None:
    # Drop audit_events
    op.drop_index(op.f("ix_audit_events_resource_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_project_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_organization_id"), table_name="audit_events")
    op.drop_table("audit_events")

    # Drop repository_snapshots
    op.drop_index(op.f("ix_repository_snapshots_commit_sha"), table_name="repository_snapshots")
    op.drop_index(op.f("ix_repository_snapshots_repository_id"), table_name="repository_snapshots")
    op.drop_table("repository_snapshots")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        snapshot_status.drop(bind, checkfirst=True)
