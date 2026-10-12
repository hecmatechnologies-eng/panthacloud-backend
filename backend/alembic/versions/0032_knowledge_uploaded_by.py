"""Record who uploaded each knowledge document

Revision ID: 0032_knowledge_uploaded_by
Revises: 0031_tool_call_approval
Create Date: 2026-10-11 00:00:00.000000

A document becomes retrievable as soon as ingestion finishes, and under semantic embeddings a
poisoned document is reachable by *meaning* rather than keyword. `KNOWLEDGE_CREATE` is held by
RoleEnum.MEMBER, the lowest org role, so the corpus a tenant's guests are answered from could be
extended by the most junior member.

The uploader was recorded only in the audit-event table, which no document read path joins. This
makes the corpus attributable without imposing an approval workflow - who added a document
should be visible before deciding whether one needs to be reviewed.

Nullable: documents may be seeded or imported without an acting user, and a null here means
"unknown origin", which the Studio can surface rather than hide.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032_knowledge_uploaded_by"
down_revision: str | None = "0031_tool_call_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("uploaded_by", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_knowledge_documents_uploaded_by",
        "knowledge_documents",
        ["uploaded_by"],
    )
    # SQLite cannot ALTER a table to add a foreign key - it has to be rebuilt by copy-and-move.
    # Without batch_alter_table this whole migration aborts on a SQLite development database,
    # leaving it stuck one revision behind and every read of knowledge_documents failing with
    # "no such column: uploaded_by". PostgreSQL needs none of this, so the migration looked fine
    # to whoever wrote it and only broke the local stack.
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.create_foreign_key(
            "fk_knowledge_documents_uploaded_by",
            "users",
            ["uploaded_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.drop_constraint("fk_knowledge_documents_uploaded_by", type_="foreignkey")
    op.drop_index("ix_knowledge_documents_uploaded_by", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "uploaded_by")