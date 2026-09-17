"""pgvector extension and vector column migration

Revision ID: 0027_pgvector_knowledge_chunks
Revises: 0026_composite_indexes
Create Date: 2026-09-17 12:30:00.000000

1. Installs pgvector extension on PostgreSQL.
2. Migrates knowledge_chunks.embedding to vector on PostgreSQL.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027_pgvector_knowledge_chunks"
down_revision: str | None = "0026_composite_indexes"
branch_labels: str | Sequence["str"] | None = None
depends_on: str | Sequence["str"] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        op.execute(
            "ALTER TABLE knowledge_chunks "
            "ALTER COLUMN embedding TYPE vector USING (embedding::text::vector);"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE knowledge_chunks "
            "ALTER COLUMN embedding TYPE json USING (embedding::text::json);"
        )
