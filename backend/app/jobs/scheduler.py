"""Scheduled maintenance jobs (ARQ cron).

The scheduler exists because two classes of work cannot be done by a request or a queued job:

- a job that must run whether or not anything is happening — nothing enqueues it, so nothing
  would ever trigger it
- a job that must not run twice concurrently — an ARQ cron is claimed by exactly one worker,
  whereas the ``asyncio.create_task`` loop in ``main.py`` runs in every uvicorn process, so the
  sweep fires once per replica

Each coroutine opens its own short-lived session. Nothing here may hold a database session open
between ticks.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from app.core.config import settings
from app.core.database import get_session_factory

logger = logging.getLogger("fussion.jobs.scheduler")


async def reap_stranded_knowledge_documents(ctx: dict | None = None) -> None:
    """Fail knowledge documents left in PROCESSING by a process death.

    ``ingest_document`` marks a document FAILED on any ordinary exception, but a SIGKILL, an OOM
    kill or a container restart skips that block entirely. The document then stays PROCESSING
    forever: never retrievable, never visibly failed, with its stored object orphaned.
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            from app.services.knowledge.reaper import reap_stale_documents

            result = await reap_stale_documents(
                db, older_than=timedelta(minutes=settings.KNOWLEDGE_REAPER_TIMEOUT_MINUTES)
            )
        except Exception:  # noqa: BLE001 - a failing cron must not kill the worker
            logger.warning("Knowledge reaper failed", exc_info=True)
            return

        if result.documents:
            logger.warning(
                "Knowledge reaper reclaimed %d stranded document(s), %d orphaned object(s), "
                "%d error(s)",
                result.documents,
                result.orphans_deleted,
                result.errors,
            )
        else:
            logger.debug("Knowledge reaper found nothing stranded")