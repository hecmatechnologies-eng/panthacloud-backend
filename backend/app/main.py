import asyncio
import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.public_cors import PublicCorsMiddleware
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import close_database_connections
from app.core.errors import register_error_handlers
from app.services.repository.executor import run_in_io_thread, shutdown_io_executor
from app.services.repository.workspace import workspace_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fussion.main")


def configure_git_provider() -> None:
    """Install the real GitHub provider.

    Until now nothing called this, so every run used the file-less `MockGitProvider` and the
    pipeline had never seen a real repository (CLAUDE.md §2). It is called from `lifespan`, which
    the test suite does not run, so tests keep the mock and cannot reach GitHub.
    """
    from app.services.integration.github import GitHubProvider, set_git_provider

    set_git_provider(GitHubProvider())
    logger.info("Git provider: GitHubProvider (real repositories)")


def configure_model_gateway() -> None:
    """Install the configured model provider, or leave the runtime failing loud.

    Called from `lifespan`, which the test suite does not run; tests install a fake gateway
    explicitly (mirroring `configure_git_provider`). With no key, the gateway stays unconfigured
    and public chat returns 503 rather than a fabricated answer (CLAUDE.md §4.10).
    """
    from app.llm.factory import build_model_gateway
    from app.llm.gateway import set_model_gateway

    gateway = build_model_gateway()
    set_model_gateway(gateway)
    if gateway is None:
        logger.warning("No model provider configured; public chat will return 503.")
    else:
        logger.info("Model gateway configured: %s", settings.MODEL_PROVIDER)


def validate_embedding_configuration() -> None:
    """Refuse an embedding configuration that would fail on the first upload or query."""
    from app.services.knowledge.embeddings import validate_embedding_configuration as validate

    validate()
    logger.info("Embedding provider: %s", settings.EMBEDDING_PROVIDER)


async def _periodic_workspace_sweep(interval_seconds: float = 900.0) -> None:
    """Periodically sweep expired workspaces in the background."""
    logger.info("Starting background workspace sweeper (interval: %ss)", interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                swept = await run_in_io_thread(workspace_manager.sweep_expired)
                if swept:
                    logger.info("Background sweep reclaimed %d expired workspace(s)", swept)
            except Exception:
                logger.warning("Background workspace sweep encountered an error", exc_info=True)
    except asyncio.CancelledError:
        logger.info("Background workspace sweeper cancelled")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Fussion Backend (%s) in %s mode", settings.APP_NAME, settings.APP_ENV)
    configure_git_provider()
    configure_model_gateway()
    validate_embedding_configuration()
    from app.agents.registry import register_default_agents

    register_default_agents()
    # A run killed before its teardown — a redeploy or an OOM mid-analysis — leaves its clone on
    # disk, and nothing else reclaims it. Startup is where a previous process's orphans are found.
    try:
        swept = workspace_manager.sweep_expired()
        if swept:
            logger.info("Swept %d expired workspace(s) at startup", swept)
    except OSError:
        # Housekeeping must never prevent the application from starting.
        logger.warning("Workspace sweep failed at startup", exc_info=True)

    # Start periodic background sweeper task for running servers
    sweeper_task = asyncio.create_task(_periodic_workspace_sweep())

    # Start embedded ARQ background worker if Redis is configured
    arq_worker = None
    arq_worker_task = None
    if settings.effective_redis_url and settings.APP_ENV != "test":
        try:
            from arq.worker import create_worker

            from app.jobs.worker import WorkerSettings

            arq_worker = create_worker(WorkerSettings)
            arq_worker_task = asyncio.create_task(arq_worker.async_run())
            logger.info("Started embedded ARQ background worker for task queue")
        except (redis.RedisError, OSError, ConnectionError, RuntimeError, ValueError) as exc:
            logger.warning("Failed to start embedded ARQ worker: %s", exc)

    try:
        yield
    finally:
        logger.info("Shutting down Fussion Backend, closing resources...")
        if arq_worker is not None:
            try:
                await arq_worker.close()
            except (redis.RedisError, OSError, ConnectionError, RuntimeError) as exc:
                logger.debug("Error closing embedded ARQ worker: %s", exc)
        if arq_worker_task is not None:
            arq_worker_task.cancel()
            try:
                await arq_worker_task
            except (asyncio.CancelledError, OSError, RuntimeError):
                pass

        sweeper_task.cancel()
        try:
            await sweeper_task
        except asyncio.CancelledError:
            pass
        shutdown_io_executor()
        from app.core.redis import close_redis
        from app.jobs.queue import close_arq_pool

        await close_arq_pool()
        await close_redis()
        await close_database_connections()


def create_application() -> FastAPI:
    app = FastAPI(
        title="Fussion Platform API",
        description="Backend Control Plane for Fussion AI Integration Engineer Platform",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Added after CORSMiddleware so it is the outermost layer. The public routes are called from a
    # customer's site, an origin this policy does not cover, so the preflight must be answered
    # before CORSMiddleware can reject it (step B8, CLAUDE.md §4.11).
    app.add_middleware(PublicCorsMiddleware)

    # Error handling
    register_error_handlers(app)

    # Root health endpoint (required by Phase 01: GET /health)
    app.include_router(health_router, tags=["health"])

    # Root GitHub App callbacks (/github/callback and /github/oauth/callback)
    from app.api.v1.endpoints import github_app
    app.include_router(github_app.router)

    # Versioned API router (/api/v1)
    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_application()
