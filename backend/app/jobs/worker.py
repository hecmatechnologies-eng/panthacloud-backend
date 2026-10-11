"""ARQ Worker configuration for Panthacloud background processing.

Run this worker container alongside the web API or as a separate service via:
    arq app.jobs.worker.WorkerSettings
"""

import logging
from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import CronJob

from app.core.config import settings
from app.jobs.scheduler import reap_stranded_knowledge_documents
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

    functions: ClassVar[list[Any]] = [
        analyze_website_integration_task,
        execute_integration_pipeline_task,
    ]
    redis_settings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 20
    job_timeout = 600  # 10 minutes maximum for heavy analyses

    # Scheduled maintenance. Registered here rather than as an asyncio loop in main.py: that
    # loop runs in every uvicorn process, so its sweep fires once per replica, while an ARQ cron
    # is claimed by exactly one worker.
    cron_jobs: ClassVar[list[Any]] = [
        # NOTE: every argument is passed explicitly because arq 0.28.0 has a bug — CronJob is a
        # dataclass whose fields carry annotations but no defaults, so all fourteen are
        # required and the natural `CronJob(name=..., coroutine=..., minute={...})` raises
        # TypeError. The Options dataclass above it in arq/cron.py has these defaulted; they
        # were not carried over. cron_jobs is unusable in 0.28.0 as shipped.
        #
        # If a newer arq fixes it this collapses to a three-line CronJob, and
        # test_arq_cron_constructor_defaults_should_be_repaired in the reaper tests should be
        # deleted — it exists to flag exactly that.
        CronJob(
            name="reap-stranded-knowledge",
            coroutine=reap_stranded_knowledge_documents,
            month=None,
            day=None,
            weekday=None,
            hour=None,
            minute={0, 15, 30, 45},  # every 15 minutes
            second=None,
            microsecond=0,
            run_at_startup=False,
            unique=True,  # claimed by exactly one worker, never run concurrently
            job_id=None,
            timeout_s=None,
            keep_result_s=None,
            keep_result_forever=None,
            max_tries=None,
        ),
    ]
