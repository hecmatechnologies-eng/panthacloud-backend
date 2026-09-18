"""Add storage_key, storage_url, and file_hash to knowledge_documents

Revision ID: 0030_knowledge_storage
Revises: 0029_origins_and_status
Create Date: 2026-09-18 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030_knowledge_storage"
down_revision: str | None = "0029_origins_and_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("storage_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("storage_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("file_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_knowledge_documents_file_hash",
        "knowledge_documents",
        ["file_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_file_hash", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "file_hash")
    op.drop_column("knowledge_documents", "storage_url")
    op.drop_column("knowledge_documents", "storage_key")
