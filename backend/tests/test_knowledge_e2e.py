"""End-to-end test case for document upload, R2/local storage, chunking,

vector generation, semantic search, and chat grounding with citations.
"""

import hashlib
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.assistant import Assistant
from app.models.knowledge import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from app.models.website_integration import WebsiteIntegration, WebsiteIntegrationStatus
from app.runtime.chat import handle_chat
from app.services.storage import get_storage_provider


def make_test_pdf(title: str, body: str) -> bytes:
    """Constructs a minimal valid PDF with extractable text."""
    content = f"BT /F1 12 Tf 10 100 Td ({title}: {body}) Tj ET".encode("latin-1")
    length = len(content)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(length).encode() + b" >> stream\n"
        + content + b"\nendstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"360\n"
        b"%%EOF\n"
    )


async def register_and_create_project(
    client: AsyncClient, email: str, org_name: str, proj_name: str, proj_slug: str
) -> tuple[str, str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test User",
            "org_name": org_name,
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]

    orgs = (await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})).json()
    org_id = orgs[0]["id"]

    p_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": proj_name, "slug": proj_slug},
    )
    assert p_resp.status_code == 201
    proj_id = p_resp.json()["id"]

    return token, org_id, proj_id


@pytest.mark.asyncio
async def test_end_to_end_knowledge_pipeline_use_case(client: AsyncClient, db_session):
    """
    End-to-end test case:
    1. Upload PDF document -> R2/local storage + text extraction + chunking + vectors
    2. Verify storage key, file hash, status READY, chunks in DB
    3. Test download endpoint -> matches raw bytes
    4. Test semantic search query -> ranks PDF chunk at rank 1
    5. Test public visitor chat -> grounds response with citation from document
    6. Delete document -> deletes from DB, cascades chunks, cleans up storage
    """
    # 1. Setup tenant
    token, org_id, proj_id = await register_and_create_project(
        client,
        email="e2e_owner@example.com",
        org_name="Acme Gadgets",
        proj_name="Smart Toaster",
        proj_slug="smart-toaster",
    )

    pdf_bytes = make_test_pdf(
        "Warranty Policy",
        "All Acme Smart Toasters include a comprehensive two-year limited warranty covering electrical failure."
    )
    expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # 2. Upload document
    upload_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("warranty_policy.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    doc_data = upload_resp.json()

    doc_id = doc_data["id"]
    assert doc_data["status"] == "READY"
    assert doc_data["filename"] == "warranty_policy.pdf"
    assert doc_data["file_hash"] == expected_hash
    assert doc_data["storage_key"] is not None
    assert f"tenants/{org_id}/projects/{proj_id}/documents/{doc_id}/warranty_policy.pdf" in doc_data["storage_key"]
    assert doc_data["chunks_count"] >= 1
    assert doc_data["download_url"] is not None

    storage = get_storage_provider()
    assert await storage.exists(doc_data["storage_key"]) is True

    # 3. Verify Database Persistence (Document + Vectors)
    doc_stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == uuid.UUID(doc_id))
    persisted_doc = (await db_session.execute(doc_stmt)).scalar_one()
    assert persisted_doc.status == DocumentStatus.READY
    assert persisted_doc.file_hash == expected_hash

    chunks_stmt = select(KnowledgeChunk).where(KnowledgeChunk.document_id == uuid.UUID(doc_id))
    chunks = (await db_session.execute(chunks_stmt)).scalars().all()
    assert len(chunks) == doc_data["chunks_count"]
    for c in chunks:
        assert len(c.embedding) > 0  # vector populated
        assert c.token_count > 0

    # 4. Test Download Endpoint
    download_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents/{doc_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download_resp.status_code == 200
    assert download_resp.content == pdf_bytes
    assert download_resp.headers["content-type"] == "application/pdf"
    assert 'filename="warranty_policy.pdf"' in download_resp.headers["content-disposition"]

    # 5. Test Semantic Retrieval Query
    query_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/knowledge/query" if False else
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "How long is the smart toaster warranty coverage?", "top_k": 3},
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert query_data["total_matches"] >= 1
    top_chunk = query_data["results"][0]
    assert top_chunk["document_filename"] == "warranty_policy.pdf"
    assert "warranty" in top_chunk["text"].lower()

    # 6. Test Public Visitor Chat with Grounded Citations
    # Setup integration, allowed origin, and assistant for the project
    from app.models.allowed_origin import AllowedOrigin

    integration = WebsiteIntegration(
        id=uuid.uuid4(),
        project_id=uuid.UUID(proj_id),
        public_key=f"pk_test_{uuid.uuid4().hex[:16]}",
        status=WebsiteIntegrationStatus.DEPLOYED,
        repository_owner="acme",
        repository_name="smart-toaster",
        default_branch="main",
    )
    db_session.add(integration)

    origin = AllowedOrigin(
        id=uuid.uuid4(),
        integration_id=integration.id,
        origin="https://acme-toaster.com",
        is_verified=True,
        source="manual",
    )
    db_session.add(origin)

    assistant = Assistant(
        id=uuid.uuid4(),
        project_id=uuid.UUID(proj_id),
        name="Acme Support Bot",
        system_instructions="You are a helpful assistant. Answer questions using the provided documents.",
        is_enabled=True,
    )
    db_session.add(assistant)
    await db_session.commit()

    # Mock ModelGateway to simulate LLM completion returning a grounded answer
    fake_reply_text = "Acme Smart Toasters include a comprehensive two-year warranty."
    mock_complete_resp = AsyncMock()
    mock_complete_resp.text = fake_reply_text

    mock_gateway = AsyncMock()
    mock_gateway.complete.return_value = mock_complete_resp

    with patch("app.runtime.chat.get_model_gateway", return_value=mock_gateway):
        chat_reply = await handle_chat(
            db_session,
            public_key=integration.public_key,
            origin="https://acme-toaster.com",
            session_id=None,
            message="What is the warranty period for the toaster?",
            client_ip="127.0.0.1",
        )

        assert chat_reply.reply == fake_reply_text
        assert len(chat_reply.citations) >= 1
        citation = chat_reply.citations[0]
        assert citation["filename"] == "warranty_policy.pdf"
        assert citation["document_id"] == doc_id

    await db_session.commit()

    # 7. Test Document Deletion with Storage Cleanup
    storage_key = doc_data["storage_key"]
    del_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # DB doc deleted
    res_after = await db_session.execute(doc_stmt)
    assert res_after.scalar_one_or_none() is None

    # DB chunks cascade deleted
    chunks_after = (await db_session.execute(chunks_stmt)).scalars().all()
    assert len(chunks_after) == 0

    # Object deleted from storage
    assert await storage.exists(storage_key) is False


@pytest.mark.asyncio
async def test_upload_rollback_cleans_storage_on_failure(client: AsyncClient, db_session):
    """If text extraction or embedding fails, storage object must be deleted during rollback."""
    token, org_id, proj_id = await register_and_create_project(
        client,
        email="fail_owner@example.com",
        org_name="Fail Corp",
        proj_name="Fail Project",
        proj_slug="fail-project",
    )

    # Valid empty markdown file with only whitespace: passes metadata check but fails extraction
    whitespace_content = b"   \n\n   \t  \n  "
    upload_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty.md", whitespace_content, "text/markdown")},
    )
    assert upload_resp.status_code == 201
    doc_data = upload_resp.json()

    assert doc_data["status"] == "FAILED"
    assert "Processing failed" in doc_data["error_message"]
    assert doc_data["storage_key"] is None  # cleared on rollback

    # Storage object was cleaned up
    storage = get_storage_provider()
    expected_key = f"tenants/{org_id}/projects/{proj_id}/documents/{doc_data['id']}/empty.md"
    assert await storage.exists(expected_key) is False
