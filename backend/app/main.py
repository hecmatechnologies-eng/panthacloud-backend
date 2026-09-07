import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Fussion Backend (%s) in %s mode", settings.APP_NAME, settings.APP_ENV)
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

    # Error handling
    register_error_handlers(app)

    # Root health endpoint (required by Phase 01: GET /health)
    app.include_router(health_router, tags=["health"])

    # Versioned API router (/api/v1)
    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_application()
