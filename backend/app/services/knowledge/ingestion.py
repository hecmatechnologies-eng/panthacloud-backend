import os
import uuid
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.knowledge import DocumentStatus, KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.models.user import User
from app.services.knowledge.chunking import extract_and_chunk
from app.services.knowledge.embeddings import get_embedding_provider

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "text/markdown",
    "text/x-markdown",
    "text/plain",
}


async def _record_audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    event_type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> None:
    """Helper to record audit events for knowledge operations."""
    try:
        event = AuditEvent(
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
            event_type=event_type,
            resource_type="knowledge_document",
            resource_id=resource_id,
            payload=payload or {},
        )
        db.add(event)
        await db.commit()
    except Exception:  # noqa: BLE001
        # Audit failure must not crash the primary operational path
        await db.rollback()


def validate_file_metadata(filename: str, content_type: str, content: bytes) -> tuple[str, str]:
    """
    Validates file extension, MIME type, file size, magic bytes, and encoding.
    Returns sanitized (filename, normalized_content_type).
    """
    # 1. Sanitize filename
    safe_filename = os.path.basename(filename or "document.txt")
    _, ext = os.path.splitext(safe_filename.lower())

    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Only PDF, Markdown (.md), and Plain Text (.txt) are supported.",
        )

    # 2. Validate file size
    file_size = len(content)
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size ({file_size} bytes) exceeds maximum allowed limit of 10 MB.",
        )
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 3. Validate MIME type
    norm_content_type = content_type.lower().split(";")[0].strip()
    if norm_content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{content_type}'.",
        )

    # 4. Consistency between extension and MIME
    if ext == ".pdf" and norm_content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type '{content_type}' does not match PDF file extension.",
        )
    if ext in (".md", ".markdown", ".txt") and norm_content_type not in (
        "text/markdown",
        "text/x-markdown",
        "text/plain",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type '{content_type}' does not match text file extension.",
        )

    # 5. Magic byte / content validation
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF file. Header does not match '%PDF-'.",
            )
    else:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid text encoding. File must be valid UTF-8 text.",
            )

    return safe_filename, norm_content_type


async def ingest_document(
    db: AsyncSession,
    kb: KnowledgeBase,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    file: UploadFile,
    current_user: User | None = None,
) -> KnowledgeDocument:
    """
    Full document ingestion pipeline:
    Validate -> Create Document (PROCESSING) -> Extract -> Chunk -> Embed -> Persist -> READY
    """
    raw_content = await file.read()
    filename = file.filename or "document.txt"
    content_type = file.content_type or "application/octet-stream"

    safe_filename, norm_content_type = validate_file_metadata(filename, content_type, raw_content)

    # Create document in DB with PROCESSING state
    doc = KnowledgeDocument(
        knowledge_base_id=kb.id,
        filename=safe_filename,
        content_type=norm_content_type,
        file_size_bytes=len(raw_content),
        status=DocumentStatus.PROCESSING,
        chunks_count=0,
        metadata_={},
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    user_id = current_user.id if current_user else None
    await _record_audit(
        db=db,
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
        event_type="knowledge.document.uploaded",
        resource_id=doc.id,
        payload={"filename": safe_filename, "file_size_bytes": len(raw_content)},
    )

    try:
        # Extract and chunk
        raw_text, extracted_chunks = extract_and_chunk(
            content_type=norm_content_type,
            raw_bytes=raw_content,
            filename=safe_filename,
        )

        if not extracted_chunks:
            raise ValueError("Document contains no extractable text content.")

        # Embed chunks with the model this knowledge base was created with, not a global default:
        # the query side resolves the same stored model.
        embedder = get_embedding_provider(kb.embedding_model, kb.embedding_dimension)
        texts = [c.text for c in extracted_chunks]
        embeddings = await embedder.embed_batch(texts)

        # Persist chunks
        for c, emb in zip(extracted_chunks, embeddings):
            chunk_row = KnowledgeChunk(
                document_id=doc.id,
                chunk_index=c.chunk_index,
                text=c.text,
                page_number=c.page_number,
                source_location=c.source_location,
                token_count=c.token_count,
                embedding=emb,
                embedding_model=embedder.model_id,
                metadata_={},
            )
            db.add(chunk_row)

        doc.raw_text = raw_text
        doc.chunks_count = len(extracted_chunks)
        doc.status = DocumentStatus.READY
        doc.error_message = None
        await db.commit()
        await db.refresh(doc)

        await _record_audit(
            db=db,
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            event_type="knowledge.document.processed",
            resource_id=doc.id,
            payload={"chunks_count": doc.chunks_count},
        )
        return doc

    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        # Mark document as FAILED with clean sanitized message
        doc.status = DocumentStatus.FAILED
        doc.error_message = f"Processing failed: {exc!s}"
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        await _record_audit(
            db=db,
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            event_type="knowledge.document.failed",
            resource_id=doc.id,
            payload={"error": doc.error_message},
        )
        return doc
