"""repositories

Revision ID: 0004_repositories
Revises: 0003_integrations
Create Date: 2026-09-08 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_repositories"
down_revision: str | None = "0003_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

repository_provider = sa.Enum("github", "gitlab", name="repository_provider")
repository_status = sa.Enum("PENDING", "CONNECTED", "DISCONNECTED", "ERROR", name="repository_status")


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("provider", repository_provider, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), server_default="main", nullable=False),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("status", repository_status, server_default="PENDING", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "external_id", name="uq_repository_integration_external_id"),
    )
    op.create_index(op.f("ix_repositories_project_id"), "repositories", ["project_id"], unique=False)
    op.create_index(op.f("ix_repositories_integration_id"), "repositories", ["integration_id"], unique=False)
    op.create_index(op.f("ix_repositories_external_id"), "repositories", ["external_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_repositories_external_id"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_integration_id"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_project_id"), table_name="repositories")
    op.drop_table("repositories")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        repository_status.drop(bind, checkfirst=True)
        repository_provider.drop(bind, checkfirst=True)
