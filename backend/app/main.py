import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.public_cors import PublicCorsMiddleware
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import close_database_connections
from app.core.errors import register_error_handlers

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Fussion Backend (%s) in %s mode", settings.APP_NAME, settings.APP_ENV)
    configure_git_provider()
    configure_model_gateway()
    validate_embedding_configuration()
    from app.agents.registry import register_default_agents

    register_default_agents()
    yield
    logger.info("Shutting down Fussion Backend, closing resources...")
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
