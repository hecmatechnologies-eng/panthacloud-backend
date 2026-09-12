"""knowledge base embedding model/dimension and message citations

Revision ID: 0015_embedding_model_citations
Revises: 0014_model_usage
Create Date: 2026-09-12 23:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_embedding_model_citations"
down_revision: str | None = "0014_model_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The dimension and model live on the knowledge base so retrieval resolves them from the
    # stored value, not a call-site constant (CLAUDE.md §6). The defaults match the pre-B6
    # deterministic provider, so existing bases and their chunks stay queryable.
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            server_default="deterministic-hash-384",
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_dimension",
            sa.Integer(),
            server_default="384",
            nullable=False,
        ),
    )
    op.add_column(
        "messages",
        sa.Column("citations", sa.JSON(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("messages", "citations")
    op.drop_column("knowledge_bases", "embedding_dimension")
    op.drop_column("knowledge_bases", "embedding_model")
