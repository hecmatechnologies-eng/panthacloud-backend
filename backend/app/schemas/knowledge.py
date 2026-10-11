import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge import DocumentStatus


class KnowledgeChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    text: str
    page_number: int | None = None
    source_location: str | None = None
    token_count: int = 0
    created_at: datetime


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    content_type: str
    file_size_bytes: int
    status: DocumentStatus
    error_message: str | None = None
    chunks_count: int = 0
    storage_key: str | None = None
    storage_url: str | None = None
    file_hash: str | None = None
    download_url: str | None = None
    # Who added this to the corpus. Surfaced so a tenant can see the origin of anything their
    # guests are answered from; null means seeded or imported, and is shown as unknown rather
    # than omitted.
    uploaded_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    chunks: list[KnowledgeChunkRead] = []


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    documents_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus
    message: str


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Search query string")
    top_k: int = Field(5, ge=1, le=50, description="Maximum number of chunks to return")
    score_threshold: float = Field(0.0, ge=0.0, le=1.0, description="Minimum cosine similarity score")


class KnowledgeQueryResultItem(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    chunk_index: int
    page_number: int | None = None
    source_location: str | None = None
    text: str
    score: float


class KnowledgeQueryResponse(BaseModel):
    query: str
    total_matches: int
    results: list[KnowledgeQueryResultItem]
