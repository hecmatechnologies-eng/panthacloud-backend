"""Scheduled reaping of stranded knowledge documents, and the ARQ cron that drives it.

``ingest_document`` marks a document FAILED on any ordinary exception. A hard process death —
SIGKILL, OOM, container restart, deploy — skips that block entirely, and nothing else reclaims
the row. These tests pin the recovery path and, incidentally, the fact that the cron exists at
all: without a scheduler, the reaper would be dead code.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.knowledge.reaper import ReapResult, reap_stale_documents


async def _seed_document(db, *, status, minutes_old: float, storage_key="tenants/x/doc.md"):
    import uuid as _uuid

    from app.models.knowledge import DocumentStatus as _Status
    from app.models.knowledge import KnowledgeDocument

    doc = KnowledgeDocument(
        id=_uuid.uuid4(),
        knowledge_base_id=_uuid.uuid4(),
        filename="policy.md",
        content_type="text/markdown",
        file_size_bytes=10,
        status=status,
        storage_key=storage_key,
        storage_url="https://example/doc.md",
    )
    db.add(doc)
    await db.flush()
    await db.execute(
        KnowledgeDocument.__table__.update()
        .where(KnowledgeDocument.id == doc.id)
        .values(
            updated_at=datetime.now(UTC) - timedelta(minutes=minutes_old),
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_old),
        )
    )
    await db.commit()
    await db.refresh(doc)
    return doc, _Status


class TestReaping:
    @pytest.mark.asyncio
    async def test_a_stranded_document_becomes_failed(self, db_session) -> None:
        from app.models.knowledge import DocumentStatus

        doc, _ = await _seed_document(
            db_session, status=DocumentStatus.PROCESSING, minutes_old=120
        )

        with patch(
            "app.services.knowledge.ingestion.delete_document_storage", new=AsyncMock()
        ):
            result = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        assert result.documents == 1
        await db_session.refresh(doc)
        assert doc.status == DocumentStatus.FAILED

    @pytest.mark.asyncio
    async def test_the_message_tells_the_tenant_to_re_upload(self, db_session) -> None:
        """A document that failed for a reason nobody recorded must say what to do next."""
        from app.models.knowledge import DocumentStatus

        doc, _ = await _seed_document(
            db_session, status=DocumentStatus.PROCESSING, minutes_old=120
        )

        with patch(
            "app.services.knowledge.ingestion.delete_document_storage", new=AsyncMock()
        ):
            await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        await db_session.refresh(doc)
        assert doc.error_message is not None
        assert "re-upload" in doc.error_message.lower()

    @pytest.mark.asyncio
    async def test_the_orphaned_object_is_deleted(self, db_session) -> None:
        """Storage cleanup lives in the exception block that never ran, so the reaper owns it."""
        from app.models.knowledge import DocumentStatus

        _, _ = await _seed_document(
            db_session,
            status=DocumentStatus.PROCESSING,
            minutes_old=120,
            storage_key="tenants/x/orphan.md",
        )
        delete = AsyncMock()

        with patch("app.services.knowledge.ingestion.delete_document_storage", new=delete):
            result = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        delete.assert_awaited_once_with("tenants/x/orphan.md")
        assert result.orphans_deleted == 1

    @pytest.mark.asyncio
    async def test_a_document_still_processing_is_left_alone(self, db_session) -> None:
        """A slow large PDF is not stranded. The timeout has to be generous for that reason."""
        from app.models.knowledge import DocumentStatus

        doc, _ = await _seed_document(db_session, status=DocumentStatus.PROCESSING, minutes_old=5)

        result = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        assert result == ReapResult(documents=0, orphans_deleted=0, errors=0)
        await db_session.refresh(doc)
        assert doc.status == DocumentStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_a_finished_document_is_never_touched(self, db_session) -> None:
        """READY documents are old by definition. Only PROCESSING can be stranded."""
        from app.models.knowledge import DocumentStatus

        doc, _ = await _seed_document(db_session, status=DocumentStatus.READY, minutes_old=10_000)

        result = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        assert result.documents == 0
        await db_session.refresh(doc)
        assert doc.status == DocumentStatus.READY

    @pytest.mark.asyncio
    async def test_a_storage_failure_still_fails_the_document(self, db_session) -> None:
        """Better a FAILED document with a live object than a PROCESSING one that looks live and
        answerable."""
        from app.models.knowledge import DocumentStatus

        doc, _ = await _seed_document(db_session, status=DocumentStatus.PROCESSING, minutes_old=120)

        with patch(
            "app.services.knowledge.ingestion.delete_document_storage",
            new=AsyncMock(side_effect=RuntimeError("storage down")),
        ):
            result = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        assert result.documents == 1
        assert result.errors == 1
        await db_session.refresh(doc)
        assert doc.status == DocumentStatus.FAILED

    @pytest.mark.asyncio
    async def test_it_is_idempotent(self, db_session) -> None:
        """Runs every 15 minutes; a second run must find nothing left to do."""
        from app.models.knowledge import DocumentStatus

        await _seed_document(db_session, status=DocumentStatus.PROCESSING, minutes_old=120)

        with patch(
            "app.services.knowledge.ingestion.delete_document_storage", new=AsyncMock()
        ):
            first = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))
            second = await reap_stale_documents(db_session, older_than=timedelta(minutes=60))

        assert first.documents == 1
        assert second.documents == 0


class TestTheSchedulerIsWired:
    """Without this the reaper is dead code — nothing would ever call it."""

    def test_the_worker_registers_the_cron(self) -> None:
        from app.jobs.worker import WorkerSettings

        names = [c.name for c in WorkerSettings.cron_jobs]
        assert "reap-stranded-knowledge" in names

    def test_the_cron_points_at_the_reaper(self) -> None:
        from app.jobs.scheduler import reap_stranded_knowledge_documents
        from app.jobs.worker import WorkerSettings

        cron = next(c for c in WorkerSettings.cron_jobs if c.name == "reap-stranded-knowledge")
        assert cron.coroutine is reap_stranded_knowledge_documents

    def test_the_cron_is_unique(self) -> None:
        """Several workers may run. Without `unique`, a slow reap could overlap itself."""
        from app.jobs.worker import WorkerSettings

        for cron in WorkerSettings.cron_jobs:
            assert cron.unique is True, f"{cron.name} would run concurrently across workers"

    def test_the_cron_actually_schedules(self) -> None:
        from app.jobs.worker import WorkerSettings

        cron = next(c for c in WorkerSettings.cron_jobs if c.name == "reap-stranded-knowledge")
        assert cron.minute == {0, 15, 30, 45}
        cron.calculate_next(datetime(2026, 10, 11, 0, 0, tzinfo=UTC))
        assert cron.next_run is not None, "a cron that never fires is worse than none"

    def test_the_existing_queue_functions_still_registered(self) -> None:
        """Adding a cron must not displace the analysis jobs."""
        from app.jobs.worker import WorkerSettings

        assert len(WorkerSettings.functions) == 2


class TestArqCronConstructorDefaultsShouldBeRepaired:
    """A canary, not a test of our code.

    arq 0.28.0 ships `CronJob` as a dataclass whose fields carry annotations but no defaults,
    so every one of the fourteen is required and the documented constructor form raises
    TypeError. `worker.py` passes all fourteen explicitly to work around it.

    When arq fixes this, this test fails - and the comment in `worker.py` plus the now-unneeded
    explicit arguments can be collapsed.
    """

    def test_the_documented_constructor_form_works(self) -> None:
        from arq.cron import CronJob

        async def noop(ctx=None):
            return None

        try:
            CronJob(name="probe", coroutine=noop, minute={0}, unique=True)
        except TypeError:
            pytest.skip(
                "arq CronJob still requires every argument; the workaround in "
                "app/jobs/worker.py is still required"
            )
        # No exception: upstream is fixed and the workaround should be simplified.
        pytest.fail(
            "arq CronJob now accepts defaults. Collapse the CronJob call in "
            "app/jobs/worker.py and delete this test."
        )