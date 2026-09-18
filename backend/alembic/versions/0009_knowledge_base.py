"""knowledge base foundation

Revision ID: 0009_knowledge_base
Revises: 0008_integration_adapters
Create Date: 2026-09-08 19:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_knowledge_base"
down_revision: str | None = "0008_integration_adapters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

document_status = sa.Enum(
    "PENDING", "PROCESSING", "READY", "FAILED",
    name="document_status",
)


def upgrade() -> None:
    # 1. Create knowledge_bases table
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_knowledge_base_project_id"),
    )
    op.create_index(op.f("ix_knowledge_bases_project_id"), "knowledge_bases", ["project_id"], unique=True)

    # 2. Create knowledge_documents table
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", document_status, server_default="PENDING", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("chunks_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_documents_knowledge_base_id"), "knowledge_documents", ["knowledge_base_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_status"), "knowledge_documents", ["status"], unique=False)

    # 3. Create knowledge_chunks table
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("source_location", sa.String(length=255), nullable=True),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_chunks_document_id"), "knowledge_chunks", ["document_id"], unique=False)
    op.create_index("ix_knowledge_chunk_doc_idx", "knowledge_chunks", ["document_id", "chunk_index"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunk_doc_idx", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")

    op.drop_index(op.f("ix_knowledge_documents_status"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_knowledge_base_id"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")

    op.drop_index(op.f("ix_knowledge_bases_project_id"), table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
