"""add token_version to users table

Revision ID: 0028_user_token_version
Revises: 0027_pgvector_knowledge_chunks
Create Date: 2026-09-17 19:30:00.000000

Adds integer column token_version to users table with server default '1' for
instant, zero-downtime global multi-device JWT revocation.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_user_token_version"
down_revision: str | None = "0027_pgvector_knowledge_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
