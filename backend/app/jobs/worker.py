"""ARQ Worker configuration for Panthacloud background processing.

Run this worker container alongside the web API or as a separate service via:
    arq app.jobs.worker.WorkerSettings
"""

import logging
from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import settings
from app.jobs.tasks import analyze_website_integration_task, execute_integration_pipeline_task

logger = logging.getLogger("fussion.jobs.worker")


def get_redis_settings() -> RedisSettings:
    url = settings.effective_redis_url or "redis://localhost:6379"
    return RedisSettings.from_dsn(url)


async def startup(ctx: dict[str, Any]) -> None:
    """Worker initialization: configure agents, git providers, and model gateways."""
    logger.info("Initializing ARQ background worker for Fussion...")
    from app.agents.registry import register_default_agents
    from app.main import configure_git_provider, configure_model_gateway

    configure_git_provider()
    configure_model_gateway()
    register_default_agents()
    logger.info("ARQ background worker initialized and ready for jobs")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown: cleanly close database pools and thread pools."""
    logger.info("Shutting down ARQ background worker...")
    from app.core.database import close_database_connections
    from app.services.repository.executor import shutdown_io_executor

    shutdown_io_executor()
    await close_database_connections()
    logger.info("ARQ worker resources cleanly released")


class WorkerSettings:
    """Settings class read by the `arq` CLI runner."""

    functions: ClassVar[list[Any]] = [analyze_website_integration_task, execute_integration_pipeline_task]
    redis_settings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 20
    job_timeout = 600  # 10 minutes maximum for heavy analyses
