from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import check_database_connectivity
from app.core.redis import check_redis_connectivity

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Service Health Check",
    description="Returns service health status. Detailed infrastructure diagnostics are redacted in production.",
)
async def health_check() -> JSONResponse:
    is_db_healthy, db_type, db_latency_ms = await check_database_connectivity()
    is_redis_healthy, redis_latency_ms = await check_redis_connectivity()

    # Redis is optional in development/test; in production if configured and down, report degraded
    has_redis = settings.effective_redis_url is not None
    redis_ok = (not has_redis) or is_redis_healthy

    overall_healthy = is_db_healthy and redis_ok
    overall_status = "healthy" if overall_healthy else "degraded"
    status_code = status.HTTP_200_OK if is_db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    payload: dict[str, Any] = {
        "status": overall_status,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }

    # In production, do not leak internal database details, type, or latency
    if settings.is_production:
        payload["database"] = {"status": "connected" if is_db_healthy else "disconnected"}
        if has_redis:
            payload["redis"] = {"status": "connected" if is_redis_healthy else "disconnected"}
    else:
        # Development / test diagnostics
        payload["environment"] = settings.APP_ENV
        payload["database"] = {
            "status": "connected" if is_db_healthy else "disconnected",
            "type": db_type,
            "latency_ms": db_latency_ms,
        }
        if has_redis:
            payload["redis"] = {
                "status": "connected" if is_redis_healthy else "disconnected",
                "latency_ms": redis_latency_ms,
            }
        else:
            payload["redis"] = {"status": "not_configured"}

    return JSONResponse(status_code=status_code, content=payload)
