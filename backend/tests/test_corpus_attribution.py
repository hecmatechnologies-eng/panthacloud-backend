"""Corpus attribution (standards-alignment.md G3).

The finding, stated precisely: a document becomes `READY` — and therefore retrievable — as soon
as ingestion finishes. Under semantic embeddings a poisoned document is reachable by *meaning*
rather than keyword, so a tenant's guests can be answered from it. `KNOWLEDGE_CREATE` is held by
`RoleEnum.MEMBER`, the lowest org role. The document row recorded no uploader at all, only a
separate audit event that no read path joins — so nothing reviewing the corpus could tell who
added what.

These tests pin attribution, and pin the policy facts the gap rests on so a future change to
`ROLE_PERMISSIONS` cannot quietly invalidate the reasoning here.
"""

import uuid
from pathlib import Path

import pytest


class TestCorpusAttributionIsRecorded:
    def test_the_document_model_carries_an_uploader(self) -> None:
        from app.models.knowledge import KnowledgeDocument

        columns = {c.name for c in KnowledgeDocument.__table__.columns}
        assert "uploaded_by" in columns

    def test_the_uploader_is_exposed_on_the_read_schema(self) -> None:
        """Attribution recorded but never surfaced would change nothing for a reviewer."""
        from app.schemas.knowledge import KnowledgeDocumentRead

        assert "uploaded_by" in KnowledgeDocumentRead.model_fields

    def test_the_column_is_nullable(self) -> None:
        """Seeded and imported documents have no acting user. Forcing a value would either break
        them or invite a placeholder that reads as a real person."""
        from app.models.knowledge import KnowledgeDocument

        column = KnowledgeDocument.__table__.columns["uploaded_by"]
        assert column.nullable is True


class TestTheMigrationMatchesTheModel:
    def test_a_migration_exists_and_follows_the_chain(self) -> None:

        versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        matches = list(versions.glob("*0032_knowledge_uploaded_by*"))
        assert len(matches) == 1, "migration file missing or duplicated"
        body = matches[0].read_text(encoding="utf-8")
        assert 'down_revision: str | None = "0031_tool_call_approval"' in body
        assert "uploaded_by" in body

        # The head migration must not already be claimed by another revision.
        heads = {
            p.read_text(encoding="utf-8").split('revision: str = "')[1].split('"')[0]
            for p in versions.glob("*.py")
            if 'revision: str = "' in p.read_text(encoding="utf-8")
        }
        assert "0032_knowledge_uploaded_by" in heads


class TestIngestionRecordsTheUploader:
    def test_the_document_is_created_with_the_acting_user(self) -> None:
        """Attribution must be set at creation. Setting it after READY leaves a window in which
        a document is retrievable but unattributed."""
        import inspect

        from app.services.knowledge import ingestion

        source = inspect.getsource(ingestion.ingest_document)
        assert "uploaded_by=current_user.id if current_user else None" in source

    def test_an_upload_without_a_user_is_recorded_as_unknown(self) -> None:
        import inspect

        from app.services.knowledge import ingestion

        source = inspect.getsource(ingestion.ingest_document)
        assert "else None" in source


class TestThePolicyThisRestsOn:
    """These are the premises of G3's remediation. They are now a decision rather than an
    observation, so they are asserted to stop drifting in either direction."""

    def test_the_owner_and_admin_manage_the_corpus(self) -> None:
        from app.core.permissions import ROLE_PERMISSIONS, Permission
        from app.models.membership import RoleEnum

        for role in (RoleEnum.OWNER, RoleEnum.ADMIN):
            perms = ROLE_PERMISSIONS[role]
            assert Permission.KNOWLEDGE_CREATE in perms, f"{role.name} must be able to upload"
            assert Permission.ASSISTANT_UPDATE in perms, f"{role.name} configures the assistant"

    def test_a_member_may_not_extend_the_corpus_guests_are_answered_from(self) -> None:
        """The remediation: knowledge upload and assistant setup are owner/admin only, because a
        READY document is immediately retrievable and semantically reachable."""
        from app.core.permissions import ROLE_PERMISSIONS, Permission
        from app.models.membership import RoleEnum

        perms = ROLE_PERMISSIONS[RoleEnum.MEMBER]
        assert Permission.KNOWLEDGE_CREATE not in perms
        assert Permission.KNOWLEDGE_DELETE not in perms
        assert Permission.ASSISTANT_CREATE not in perms
        assert Permission.ASSISTANT_UPDATE not in perms
        assert Permission.ASSISTANT_DELETE not in perms

    def test_a_member_still_gets_the_read_only_views(self) -> None:
        """Restricting mutation must not silently turn a member into a viewer."""
        from app.core.permissions import ROLE_PERMISSIONS, Permission
        from app.models.membership import RoleEnum

        perms = ROLE_PERMISSIONS[RoleEnum.MEMBER]
        assert Permission.KNOWLEDGE_VIEW in perms
        assert Permission.ASSISTANT_VIEW in perms

    def test_a_viewer_can_still_see_the_corpus(self) -> None:
        from app.core.permissions import ROLE_PERMISSIONS, Permission
        from app.models.membership import RoleEnum

        perms = ROLE_PERMISSIONS[RoleEnum.VIEWER]
        assert Permission.KNOWLEDGE_VIEW in perms
        assert Permission.KNOWLEDGE_CREATE not in perms

    def test_uploading_makes_a_document_retrievable_without_review(self) -> None:
        """The document goes straight to READY. A review gate would change this, so this test
        fails loudly when someone adds one and the gap's remediation has landed."""
        from app.models.knowledge import DocumentStatus

        assert DocumentStatus.READY.name == "READY"
        statuses = {member.name for member in DocumentStatus}
        assert not statuses & {"PENDING_REVIEW", "AWAITING_REVIEW", "NEEDS_REVIEW"}, (
            f"a review state now exists ({sorted(statuses)}); update the G3 remediation"
        )

    def test_retrieval_reads_chunks_not_the_stored_file(self) -> None:
        """So storage tampering does not reach guests; the *content* of the chunk is the
        attack surface, which is why attribution matters more than hashing."""
        import inspect

        from app.services.knowledge import retrieval

        source = inspect.getsource(retrieval.query_knowledge_base)
        assert "chunk.text" in source
        assert "download" not in source and "storage" not in source.lower()


@pytest.mark.asyncio
async def test_a_uploaded_document_is_retrievable_and_attributable(db_session) -> None:
    """The end-to-end shape of the gap, made concrete."""
    from sqlalchemy import select

    from app.models.knowledge import DocumentStatus, KnowledgeBase, KnowledgeDocument
    from app.models.organization import Organization
    from app.models.project import Project
    from app.models.user import User

    org = Organization(id=uuid.uuid4(), name="Corpus Org", slug=f"corpus-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Corpus Project",
        slug=f"corpus-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(project)
    uploader = User(
        id=uuid.uuid4(),
        email=f"uploader-{uuid.uuid4().hex[:6]}@khotels.co.ug",
        full_name="Junior Member",
        hashed_password="pw",
    )
    db_session.add(uploader)
    await db_session.flush()

    kb = KnowledgeBase(
        id=uuid.uuid4(),
        project_id=project.id,
        name="Corpus",
        embedding_model="deterministic-hash-384",
        embedding_dimension=384,
    )
    db_session.add(kb)
    await db_session.flush()

    doc = KnowledgeDocument(
        knowledge_base_id=kb.id,
        filename="policy.md",
        content_type="text/markdown",
        file_size_bytes=10,
        status=DocumentStatus.READY,
        file_hash="abc123",
        uploaded_by=uploader.id,
    )
    db_session.add(doc)
    await db_session.commit()

    stored = (await db_session.execute(select(KnowledgeDocument))).scalar_one()
    assert stored.uploaded_by == uploader.id, "a reviewer must be able to see who added this"
    assert stored.status == DocumentStatus.READY, "and it is live to guests immediately"