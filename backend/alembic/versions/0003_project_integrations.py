"""project integrations

Revision ID: 0003_integrations
Revises: 0002_identity
Create Date: 2026-09-08 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_integrations"
down_revision: str | None = "0002_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

integration_provider = sa.Enum("github", "gitlab", "external_api", "webhook", name="integration_provider")
integration_status = sa.Enum("PENDING", "ACTIVE", "DISCONNECTED", "ERROR", "DISABLED", name="integration_status")


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", integration_provider, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", integration_status, server_default="PENDING", nullable=False),
        sa.Column("configuration", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("encrypted_secrets", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_integration_project_name"),
    )
    op.create_index(op.f("ix_integrations_project_id"), "integrations", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integrations_project_id"), table_name="integrations")
    op.drop_table("integrations")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        integration_status.drop(bind, checkfirst=True)
        integration_provider.drop(bind, checkfirst=True)
