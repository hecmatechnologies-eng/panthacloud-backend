"""github app link on a website integration

Revision ID: 0022_integration_installation
Revises: 0021_github_installations
Create Date: 2026-09-13 07:00:00.000000

Step E2: an integration connected through the GitHub App records the installation id instead of a
PAT. Nullable: a PAT-linked or public integration has none.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_integration_installation"
down_revision: str | None = "0021_github_installations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "website_integrations",
        sa.Column("github_installation_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("website_integrations") as batch_op:
        batch_op.drop_column("github_installation_id")
