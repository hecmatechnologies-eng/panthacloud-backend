"""ARQ job queue client for enqueuing background tasks.

Provides high-level dispatching functions for the web API layer to queue heavy work.
Gracefully falls back to direct execution or in-process background tasks when Redis is unconfigured.
"""

import logging
import uuid
from typing import Any

import redis
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

logger = logging.getLogger("fussion.jobs.queue")

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis | None:
    """Return an active ArqRedis pool connection, or None if Redis is unconfigured."""
    global _arq_pool
    url = settings.effective_redis_url
    if not url:
        return None

    if _arq_pool is None:
        try:
            settings_obj = RedisSettings.from_dsn(url)
            _arq_pool = await create_pool(settings_obj)
            logger.info("Connected to ARQ Redis task queue")
        except (redis.RedisError, OSError, ConnectionError, RuntimeError, ValueError) as exc:
            logger.warning("Failed to connect to ARQ Redis queue: %s", exc)
            return None

    return _arq_pool


async def close_arq_pool() -> None:
    """Close ARQ client connection pool during application teardown."""
    global _arq_pool
    if _arq_pool is not None:
        try:
            await _arq_pool.aclose()
        except (redis.RedisError, OSError, ConnectionError, RuntimeError) as exc:
            logger.debug("Error closing ARQ pool: %s", exc)
        _arq_pool = None


async def enqueue_analysis(
    org_id: uuid.UUID | str,
    proj_id: uuid.UUID | str,
    integration_id: uuid.UUID | str,
) -> str | None:
    """Enqueue a repository analysis job into ARQ.

    Returns the job ID if queued, or None if ARQ Redis is unconfigured.
    """
    pool = await get_arq_pool()
    if pool is not None:
        try:
            job = await pool.enqueue_job(
                "analyze_website_integration_task",
                str(org_id),
                str(proj_id),
                str(integration_id),
            )
            logger.info("Enqueued analysis job %s for integration %s", job.job_id, integration_id)
            return job.job_id
        except (redis.RedisError, OSError, ConnectionError, RuntimeError, ValueError) as exc:
            logger.warning("Failed to enqueue analysis job to ARQ: %s", exc)
            return None
    return None


async def enqueue_pipeline_execution(
    org_id: uuid.UUID | str,
    proj_id: uuid.UUID | str,
    integration_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None = None,
) -> str | None:
    """Enqueue an integration pipeline execution job into ARQ.

    Returns the job ID if queued, or None if ARQ Redis is unconfigured.
    """
    pool = await get_arq_pool()
    if pool is not None:
        try:
            job = await pool.enqueue_job(
                "execute_integration_pipeline_task",
                str(org_id),
                str(proj_id),
                str(integration_id),
                str(user_id) if user_id else None,
            )
            logger.info("Enqueued pipeline execution job %s for integration %s", job.job_id, integration_id)
            return job.job_id
        except (redis.RedisError, OSError, ConnectionError, RuntimeError, ValueError) as exc:
            logger.warning("Failed to enqueue pipeline job to ARQ: %s", exc)
            return None
    return None


async def get_job_info(job_id: str) -> dict[str, Any] | None:
    """Retrieve status and result of an ARQ job."""
    from arq.jobs import Job, JobStatus

    pool = await get_arq_pool()
    if pool is None:
        return None

    try:
        job = Job(job_id, pool)
        status = await job.status()
        status_str = status.value if isinstance(status, JobStatus) else str(status)
        info: dict[str, Any] = {
            "job_id": job_id,
            "status": status_str,
        }
        if status == JobStatus.complete:
            try:
                info["result"] = await job.result(timeout=0)
            except TimeoutError:
                pass
        return info
    except (redis.RedisError, OSError, ConnectionError, RuntimeError, ValueError) as exc:
        logger.warning("Failed to query job %s info: %s", job_id, exc)
        return None
