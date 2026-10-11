"""Reap knowledge documents stranded in PROCESSING by a hard process death.

``ingest_document`` catches ``Exception`` and marks the document ``FAILED``, which covers every
ordinary failure: a parse error, an embedding provider outage, a storage error. What it cannot
cover is the process going away mid-ingestion — SIGKILL, an OOM kill, a container restart, a
deploy. The ``except`` block never runs, and the document stays ``PROCESSING`` forever:

- never ``READY``, so it is silently absent from every answer
- never ``FAILED``, so an admin looking at the list sees a document that looks like it is still
  working
- its stored object is orphaned, because storage cleanup lives in the same ``except`` block

Nothing else reclaims it. This module is the reaper, and the scheduler is what calls it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DocumentStatus, KnowledgeDocument

logger = logging.getLogger("fussion.knowledge.reaper")


@dataclass(frozen=True, slots=True)
class ReapResult:
    documents: int
    orphans_deleted: int
    errors: int


async def reap_stale_documents(
    db: AsyncSession, *, older_than: timedelta, now: datetime | None = None
) -> ReapResult:
    """Mark documents stuck in PROCESSING as FAILED, and delete their orphaned storage.

    Idempotent: a document already past the threshold and still ``PROCESSING`` is reaped once,
    then never again because its status changes. Safe to run from several workers.
    """
    moment = now or datetime.now(UTC)
    cutoff = moment - older_than

    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.status == DocumentStatus.PROCESSING,
        KnowledgeDocument.updated_at < cutoff,
    )
    stranded = (await db.execute(stmt)).scalars().all()

    if not stranded:
        return ReapResult(documents=0, orphans_deleted=0, errors=0)

    logger.warning(
        "Reaping %d knowledge document(s) stuck in PROCESSING since before %s",
        len(stranded),
        cutoff.isoformat(),
    )

    orphans = 0
    errors = 0

    for doc in stranded:
        # Delete the stored object first: if this fails we would rather leave a FAILED document
        # with a live object than a PROCESSING one that looks live and answerable.
        if doc.storage_key:
            try:
                from app.services.knowledge.ingestion import delete_document_storage

                await delete_document_storage(doc.storage_key)
                orphans += 1
            except Exception:
                errors += 1
                logger.warning(
                    "Could not delete orphaned storage for document %s", doc.id, exc_info=True
                )
        doc.storage_key = None
        doc.storage_url = None
        doc.status = DocumentStatus.FAILED
        doc.error_message = (
            "Processing did not complete: the process ended before ingestion finished. "
            "Re-upload the document."
        )

    await db.commit()

    for doc in stranded:
        logger.warning("Reaped stranded document %s (%s)", doc.id, doc.filename)

    return ReapResult(documents=len(stranded), orphans_deleted=orphans, errors=errors)