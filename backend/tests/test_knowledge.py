import math
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.knowledge.chunking import extract_and_chunk
from app.services.knowledge.embeddings import DeterministicHashEmbeddingProvider, cosine_similarity


def make_test_pdf_bytes(text: str) -> bytes:
    """Constructs a minimal valid PDF with an extractable text stream."""
    content = f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
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


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": f"{name}'s Org",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    user_id = data["user"]["id"]

    orgs_resp = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_resp.json()[0]["id"]
    return token, user_id, org_id


async def create_project(client: AsyncClient, token: str, org_id: str, name: str, slug: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": slug},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================================
# 1. Deterministic Embeddings Unit Tests
# ============================================================================


async def test_embeddings_properties():
    provider = DeterministicHashEmbeddingProvider(dimension=384)
    assert provider.dimension == 384
    assert provider.model_id == "deterministic-hash-384"

    text = "Fussion AI integration engineer for customer websites"
    emb1 = await provider.embed_text(text)
    emb2 = await provider.embed_text(text)

    # Identical text -> identical vector
    assert emb1 == emb2
    assert len(emb1) == 384

    # Unit length (norm == 1)
    norm = math.sqrt(sum(x * x for x in emb1))
    assert math.isclose(norm, 1.0, rel_tol=1e-3)

    # Cosine similarity identical = 1.0
    sim_self = cosine_similarity(emb1, emb2)
    assert math.isclose(sim_self, 1.0, rel_tol=1e-3)

    # Semantic similarity: related texts have higher score than unrelated
    related_text = "AI engineer integration for customer storefront websites"
    unrelated_text = "Photosynthesis chlorophyll plant biology light absorption"

    emb_rel = await provider.embed_text(related_text)
    emb_unrel = await provider.embed_text(unrelated_text)

    sim_rel = cosine_similarity(emb1, emb_rel)
    sim_unrel = cosine_similarity(emb1, emb_unrel)

    assert sim_rel > sim_unrel


async def test_default_embedding_provider_and_resolution():
    """The dimension/model come from settings and the KB, never a call-site constant."""
    from app.services.knowledge.embeddings import (
        build_default_embedding_provider,
        get_embedding_provider,
    )

    default = build_default_embedding_provider()
    assert default.model_id == "deterministic-hash-384"
    assert default.dimension == 384

    resolved = get_embedding_provider("deterministic-hash-384", 384)
    assert resolved.model_id == "deterministic-hash-384"
    assert len(await resolved.embed_text("hello")) == 384


def test_validate_embedding_configuration_rejects_unknown_model(monkeypatch):
    from app.core.config import settings
    from app.services.knowledge.embeddings import validate_embedding_configuration

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "text-embedding-004")
    with pytest.raises(RuntimeError):
        validate_embedding_configuration()


# ============================================================================
# 2. Deterministic Chunking Unit Tests
# ============================================================================


def test_chunking_determinism():
    md_content = b"# Product Overview\n\nFussion is an automated integration tool.\n\n## Refund Policy\n\nCustomers may request a full refund within 30 days of purchase.\n\n### Exceptions\n\nCustom enterprise deployments are non-refundable."

    raw1, chunks1 = extract_and_chunk("text/markdown", md_content, "policy.md")
    raw2, chunks2 = extract_and_chunk("text/markdown", md_content, "policy.md")

    assert raw1 == raw2
    assert len(chunks1) == len(chunks2)
    assert len(chunks1) >= 2

    # Check sequential indices
    for i, c in enumerate(chunks1):
        assert c.chunk_index == i
        assert c.text == chunks2[i].text
        assert c.source_location == chunks2[i].source_location

    # Check heading preservation
    locations = [c.source_location for c in chunks1]
    assert any("Heading: Refund Policy" in loc for loc in locations if loc)


# ============================================================================
# 3. Document Upload Lifecycle Tests (Markdown, PDF, Plain Text)
# ============================================================================


@pytest.mark.asyncio
async def test_upload_markdown_document(client: AsyncClient):
    token, _, org_id = await register_user(client, "md_user@example.com", "MD User")
    proj_id = await create_project(client, token, org_id, "Storefront", "storefront-md")

    md_content = (
        b"# Customer Support Guidelines\n\n"
        b"Our support team is available 24/7 to resolve technical integration inquiries.\n\n"
        b"## SLAs\n\n"
        b"Urgent issues receive an initial response within 15 minutes."
    )

    files = {"file": ("support.md", md_content, "text/markdown")}
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "support.md"
    assert data["content_type"] == "text/markdown"
    assert data["status"] == "READY"
    assert data["chunks_count"] >= 2
    assert len(data["chunks"]) >= 2
    assert data["chunks"][0]["chunk_index"] == 0
    assert data["chunks"][0]["source_location"] is not None


@pytest.mark.asyncio
async def test_upload_pdf_document(client: AsyncClient):
    token, _, org_id = await register_user(client, "pdf_user@example.com", "PDF User")
    proj_id = await create_project(client, token, org_id, "PDF Store", "storefront-pdf")

    pdf_bytes = make_test_pdf_bytes("Terms and Conditions of Service")
    files = {"file": ("terms.pdf", pdf_bytes, "application/pdf")}

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "terms.pdf"
    assert data["status"] == "READY"
    assert data["chunks_count"] >= 1
    assert data["chunks"][0]["page_number"] == 1
    assert data["chunks"][0]["source_location"] == "Page 1"


@pytest.mark.asyncio
async def test_upload_plain_text_document(client: AsyncClient):
    token, _, org_id = await register_user(client, "txt_user@example.com", "TXT User")
    proj_id = await create_project(client, token, org_id, "TXT Store", "storefront-txt")

    txt_bytes = b"Welcome to our business.\n\nWe provide cutting edge e-commerce integrations."
    files = {"file": ("readme.txt", txt_bytes, "text/plain")}

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "readme.txt"
    assert data["status"] == "READY"
    assert data["chunks_count"] >= 1


# ============================================================================
# 4. Upload Rejection & Security Invariants
# ============================================================================


@pytest.mark.asyncio
async def test_upload_unsupported_format_rejected(client: AsyncClient):
    token, _, org_id = await register_user(client, "bad_fmt@example.com", "Bad Fmt")
    proj_id = await create_project(client, token, org_id, "Sec Test", "sec-test")

    # .exe rejection
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("malware.exe", b"MZbinarycontent", "application/x-msdownload")},
    )
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]

    # .jpg rejection
    resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", b"\xff\xd8\xffimagecontent", "image/jpeg")},
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_upload_mime_mismatch_rejected(client: AsyncClient):
    token, _, org_id = await register_user(client, "mismatch@example.com", "Mismatch User")
    proj_id = await create_project(client, token, org_id, "Mismatch", "mismatch-proj")

    # Extension says .pdf but MIME says text/plain
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fake.pdf", b"just plain text", "text/plain")},
    )
    assert resp.status_code == 400

    # Extension says .txt but MIME says application/pdf
    resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fake.txt", b"%PDF-1.4...", "application/pdf")},
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_upload_invalid_pdf_magic_bytes_rejected(client: AsyncClient):
    token, _, org_id = await register_user(client, "fake_pdf@example.com", "Fake PDF")
    proj_id = await create_project(client, token, org_id, "Fake PDF Proj", "fake-pdf")

    # MIME is application/pdf and extension is .pdf, but does not start with %PDF-
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("corrupt.pdf", b"NOT_A_PDF_STREAM", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Invalid PDF" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_file_size_limit_rejected(client: AsyncClient):
    token, _, org_id = await register_user(client, "big_file@example.com", "Big File")
    proj_id = await create_project(client, token, org_id, "Big File Proj", "big-file")

    # File size > 10 MB (10 * 1024 * 1024 + 10 bytes)
    big_content = b"A" * (10 * 1024 * 1024 + 10)
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("large.txt", big_content, "text/plain")},
    )
    assert resp.status_code == 400
    assert "exceeds maximum allowed limit of 10 MB" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_failed_processing_state(client: AsyncClient):
    token, _, org_id = await register_user(client, "failed_doc@example.com", "Fail User")
    proj_id = await create_project(client, token, org_id, "Fail Proj", "fail-proj")

    # File with whitespace only passes initial size/encoding checks but fails text extraction
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty_whitespace.md", b"   \n\n   \t  \n  ", "text/markdown")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "FAILED"
    assert "Processing failed" in data["error_message"]
    assert data["chunks_count"] == 0


# ============================================================================
# 5. Semantic Retrieval & Grounding Tests
# ============================================================================


@pytest.mark.asyncio
async def test_semantic_retrieval_ranking(client: AsyncClient):
    token, _, org_id = await register_user(client, "searcher@example.com", "Search User")
    proj_id = await create_project(client, token, org_id, "E-Commerce", "e-comm")

    # Upload Doc 1: Shipping and Refunds
    doc1_content = (
        b"# Shipping and Returns Policy\n\n"
        b"## Refund Policy\n\n"
        b"Customers may initiate a full refund within thirty days of receiving their physical merchandise.\n\n"
        b"## Shipping Rates\n\n"
        b"Standard shipping takes three to five business days across North America."
    )
    r1 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("shipping_refunds.md", doc1_content, "text/markdown")},
    )
    assert r1.status_code == 201

    # Upload Doc 2: Developer Authentication
    doc2_content = (
        b"# Developer API Guide\n\n"
        b"## Authentication\n\n"
        b"API clients must include a Bearer JWT access token in the HTTP Authorization header.\n\n"
        b"## Rate Limiting\n\n"
        b"Requests are throttled to 100 requests per minute per IP."
    )
    r2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("api_guide.md", doc2_content, "text/markdown")},
    )
    assert r2.status_code == 201

    # Query 1: "What is your refund policy?"
    query_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "What is your refund policy for customers?", "top_k": 3},
    )
    assert query_resp.status_code == 200
    res_data = query_resp.json()
    assert res_data["total_matches"] >= 1
    top_result = res_data["results"][0]

    # Rank 1 must be the refund policy chunk!
    assert top_result["document_filename"] == "shipping_refunds.md"
    assert "Heading: Refund Policy" in top_result["source_location"]
    assert "refund" in top_result["text"].lower()

    # Query 2: "Bearer JWT tokens"
    query_resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "Bearer JWT token authentication header", "top_k": 3},
    )
    assert query_resp2.status_code == 200
    top_result2 = query_resp2.json()["results"][0]
    assert top_result2["document_filename"] == "api_guide.md"
    assert "Heading: Authentication" in top_result2["source_location"]


# ============================================================================
# 6. Multi-Tenant and Multi-Project Isolation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cross_tenant_and_cross_project_isolation(client: AsyncClient):
    token_a, _, org_a = await register_user(client, "tenant_a@example.com", "Tenant A")
    token_b, _, org_b = await register_user(client, "tenant_b@example.com", "Tenant B")

    proj_a = await create_project(client, token_a, org_a, "Project Alpha", "proj-alpha")
    proj_b = await create_project(client, token_b, org_b, "Project Beta", "proj-beta")

    # Tenant A uploads a document
    doc_resp = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/knowledge/documents",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("secret_plans.md", b"# Top Secret Plans\n\nConfidential Alpha strategy.", "text/markdown")},
    )
    assert doc_resp.status_code == 201
    doc_a_id = doc_resp.json()["id"]

    # Tenant B tries to access Tenant A's document list -> 404 (anti-enumeration)
    cross_list = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/knowledge/documents",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_list.status_code == 404

    # Tenant B tries to get Tenant A's specific document -> 404
    cross_doc = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/knowledge/documents/{doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_doc.status_code == 404

    # Tenant B tries to delete Tenant A's document -> 404
    cross_del = await client.delete(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/knowledge/documents/{doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_del.status_code == 404

    # Tenant B queries Project B knowledge -> must NOT return any chunks from Project A
    b_query = await client.post(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/knowledge/query",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"query": "Top Secret Plans Confidential Alpha", "top_k": 5},
    )
    assert b_query.status_code == 200
    assert b_query.json()["total_matches"] == 0


# ============================================================================
# 7. RBAC Authorization Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rbac_knowledge_permissions(client: AsyncClient):
    # Register Owner
    owner_token, _, org_id = await register_user(client, "kb_owner@example.com", "KB Owner")
    proj_id = await create_project(client, owner_token, org_id, "RBAC Proj", "rbac-proj")

    # Register Viewer user
    viewer_token, _, _ = await register_user(client, "kb_viewer@example.com", "KB Viewer")

    # Add viewer to Owner's org as VIEWER
    add_viewer_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "kb_viewer@example.com", "role": "VIEWER"},
    )
    assert add_viewer_resp.status_code == 201

    # 1. VIEWER attempts upload -> 403 Forbidden
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {viewer_token}"},
        files={"file": ("unauthorized.md", b"# Not Allowed", "text/markdown")},
    )
    assert resp.status_code == 403

    # 2. OWNER uploads document -> 201 Created
    owner_upload = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("authorized.md", b"# Authorized Manual\n\nContent for testing.", "text/markdown")},
    )
    assert owner_upload.status_code == 201
    doc_id = owner_upload.json()["id"]

    # 3. VIEWER can view document list -> 200 OK
    v_list = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_list.status_code == 200
    assert len(v_list.json()) == 1

    # 4. VIEWER can get document details -> 200 OK
    v_detail = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_detail.status_code == 200

    # 5. VIEWER can query knowledge -> 200 OK
    v_query = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/query",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"query": "Authorized Manual", "top_k": 2},
    )
    assert v_query.status_code == 200

    # 6. VIEWER attempts delete -> 403 Forbidden
    v_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_del.status_code == 403


# ============================================================================
# 8. Cascade Deletion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_document_cascade_deletion(client: AsyncClient):
    from app.core.database import get_session_factory

    token, _, org_id = await register_user(client, "cascade_user@example.com", "Cascade User")
    proj_id = await create_project(client, token, org_id, "Cascade Proj", "cascade-proj")

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("to_delete.md", b"# To Delete\n\nChunk 1\n\n## Section 2\n\nChunk 2", "text/markdown")},
    )
    assert resp.status_code == 201
    doc_id = uuid.UUID(resp.json()["id"])

    # Verify chunks exist in database
    session_factory = get_session_factory()
    async with session_factory() as db:
        chunks_stmt = select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        chunks_res = await db.execute(chunks_stmt)
        assert len(chunks_res.scalars().all()) >= 2

    # Delete document
    del_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/knowledge/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # Verify document is gone
    async with session_factory() as db:
        doc_stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        doc_res = await db.execute(doc_stmt)
        assert doc_res.scalar_one_or_none() is None

        # Verify chunks are cascaded and gone
        chunks_after = await db.execute(chunks_stmt)
        assert len(chunks_after.scalars().all()) == 0

