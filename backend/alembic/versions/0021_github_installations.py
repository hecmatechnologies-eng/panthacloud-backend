"""github app installations

Revision ID: 0021_github_installations
Revises: 0020_run_change_set
Create Date: 2026-09-13 06:00:00.000000

Step E1: a GitHub App installation linked to an organization. The credential is not stored — an
installation access token is minted on demand.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_github_installations"
down_revision: str | None = "0020_run_change_set"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "github_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False, server_default="User"),
        sa.Column("repository_selection", sa.String(length=20), nullable=False, server_default="selected"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_github_installations_organization_id"),
        "github_installations",
        ["organization_id"],
        unique=False,
    )
    # Unique index, matching the model's `unique=True, index=True`.
    op.create_index(
        op.f("ix_github_installations_installation_id"),
        "github_installations",
        ["installation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_github_installations_installation_id"), table_name="github_installations")
    op.drop_index(op.f("ix_github_installations_organization_id"), table_name="github_installations")
    op.drop_table("github_installations")
