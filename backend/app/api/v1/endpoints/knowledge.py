import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_current_knowledge_document,
    get_current_user,
    get_or_create_knowledge_base,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeChunkRead,
    KnowledgeDocumentRead,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
)
from app.services.knowledge.ingestion import delete_document_storage, ingest_document
from app.services.knowledge.retrieval import query_knowledge_base
from app.services.storage import StorageNotFoundError, get_storage_provider

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/knowledge",
    tags=["Knowledge Base"],
)


def _to_doc_read(
    doc: KnowledgeDocument,
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> KnowledgeDocumentRead:
    chunks_read = [
        KnowledgeChunkRead(
            id=c.id,
            chunk_index=c.chunk_index,
            text=c.text,
            page_number=c.page_number,
            source_location=c.source_location,
            token_count=c.token_count,
            created_at=c.created_at,
        )
        for c in (doc.chunks or [])
    ]
    download_url = None
    if org_id and project_id and doc.storage_key:
        download_url = f"/api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents/{doc.id}/download"

    return KnowledgeDocumentRead(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        content_type=doc.content_type,
        file_size_bytes=doc.file_size_bytes,
        status=doc.status,
        error_message=doc.error_message,
        chunks_count=doc.chunks_count,
        storage_key=doc.storage_key,
        storage_url=doc.storage_url,
        file_hash=doc.file_hash,
        download_url=download_url,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        chunks=chunks_read,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a knowledge document",
)
async def upload_document(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.KNOWLEDGE_CREATE)),
    ],
    kb: Annotated[KnowledgeBase, Depends(get_or_create_knowledge_base)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeDocumentRead:
    """
    Upload and ingest a supported business document (PDF, Markdown, Plain Text).
    Enforces 10 MB limit and safe deterministic extraction/chunking/embedding.
    """
    doc = await ingest_document(
        db=db,
        kb=kb,
        org_id=org_id,
        project_id=project_id,
        file=file,
        current_user=current_user,
    )
    # Load chunks for read model
    stmt = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.id == doc.id)
        .options(selectinload(KnowledgeDocument.chunks))
    )
    res = await db.execute(stmt)
    refreshed_doc = res.scalar_one()
    return _to_doc_read(refreshed_doc, org_id, project_id)


@router.get(
    "/documents",
    response_model=list[KnowledgeDocumentRead],
    summary="List knowledge documents for the project",
)
async def list_documents(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.KNOWLEDGE_VIEW)),
    ],
    kb: Annotated[KnowledgeBase, Depends(get_or_create_knowledge_base)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[KnowledgeDocumentRead]:
    """
    Lists all documents in the project's knowledge base.
    """
    stmt = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.knowledge_base_id == kb.id)
        .options(selectinload(KnowledgeDocument.chunks))
        .order_by(KnowledgeDocument.created_at.desc())
    )
    result = await db.execute(stmt)
    docs = result.scalars().all()
    return [_to_doc_read(d, org_id, project_id) for d in docs]


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentRead,
    summary="Get knowledge document details and chunks",
)
async def get_document(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.KNOWLEDGE_VIEW)),
    ],
    doc: Annotated[KnowledgeDocument, Depends(get_current_knowledge_document)],
) -> KnowledgeDocumentRead:
    """
    Returns document metadata and extracted chunks with citations.
    """
    return _to_doc_read(doc, org_id, project_id)


@router.get(
    "/documents/{document_id}/download",
    summary="Download the raw uploaded document",
)
async def download_document(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.KNOWLEDGE_VIEW)),
    ],
    doc: Annotated[KnowledgeDocument, Depends(get_current_knowledge_document)],
) -> Response:
    """
    Download raw original document file from object storage (R2 or local).
    """
    if not doc.storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document storage file not found",
        )
    storage = get_storage_provider()
    try:
        data = await storage.download(doc.storage_key)
    except StorageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage object not found",
        ) from exc
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "Content-Length": str(len(data)),
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge document and its chunks",
)
async def delete_document(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.KNOWLEDGE_DELETE)),
    ],
    doc: Annotated[KnowledgeDocument, Depends(get_current_knowledge_document)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """
    Deletes a knowledge document, removes its object from storage, and cascades
    deletion to all associated chunks.
    """
    storage_key = doc.storage_key
    await db.delete(doc)
    await db.commit()
    await delete_document_storage(storage_key)


@router.post(
    "/query",
    response_model=KnowledgeQueryResponse,
    summary="Semantic query against project knowledge base",
)
async def query_knowledge(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    request: KnowledgeQueryRequest,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.KNOWLEDGE_VIEW)),
    ],
    kb: Annotated[KnowledgeBase, Depends(get_or_create_knowledge_base)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeQueryResponse:
    """
    Performs semantic retrieval against all READY chunks in the project's knowledge base.
    Returns ranked citations without exposing vector embeddings.
    """
    return await query_knowledge_base(db=db, kb=kb, request=request)
