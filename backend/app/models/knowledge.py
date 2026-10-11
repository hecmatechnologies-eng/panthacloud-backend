import enum
import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.project import Project

# JSON type that falls back gracefully across PostgreSQL and SQLite
JSONType = JSON().with_variant(JSONB, "postgresql")
# Vector type with native pgvector in PostgreSQL and fallback to JSON in SQLite
VectorColumnType = Vector().with_variant(JSON(), "sqlite")


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class KnowledgeBase(BaseModel):
    __tablename__ = "knowledge_bases"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # The embedding model and dimension this base's chunks were embedded with. Stored here, not
    # hardcoded at the retrieval call site, so a query always uses the same model as the chunks
    # (CLAUDE.md §6, connascence). Defaults match the pre-B6 deterministic provider so existing
    # bases stay queryable; new bases take the configured provider.
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        default="deterministic-hash-384",
        server_default="deterministic-hash-384",
        nullable=False,
    )
    embedding_dimension: Mapped[int] = mapped_column(
        Integer,
        default=384,
        server_default="384",
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="knowledge_base",
    )
    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        "KnowledgeDocument",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        order_by="KnowledgeDocument.created_at.desc()",
    )


class KnowledgeDocument(BaseModel):
    __tablename__ = "knowledge_documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    raw_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    chunks_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    storage_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    # Who added this to the corpus. A READY document is retrievable and, under semantic
    # embeddings, reachable by meaning rather than keyword, so the guests of a tenant can be
    # answered from it. KNOWLEDGE_CREATE is held by the lowest org role, which makes attribution
    # a precondition for reviewing the corpus at all. Nullable: seeded or imported documents may
    # have no acting user, and "unknown origin" should be visible rather than absent.
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONType,
        default=dict,
        nullable=False,
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase",
        back_populates="documents",
    )
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index.asc()",
    )


class KnowledgeChunk(BaseModel):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    source_location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        VectorColumnType,
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONType,
        default=dict,
        nullable=False,
    )

    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
    )

    __table_args__ = (
        Index("ix_knowledge_chunk_doc_idx", "document_id", "chunk_index"),
    )
