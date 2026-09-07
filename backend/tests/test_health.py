import pytest
from httpx import AsyncClient

from app.core.config import Settings


@pytest.mark.asyncio
async def test_root_health_endpoint(client: AsyncClient):
    """Verify that root GET /health returns 200 and valid status structure."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "fussion-backend"
    assert "database" in data
    assert data["database"]["status"] == "connected"


@pytest.mark.asyncio
async def test_api_v1_health_endpoint(client: AsyncClient):
    """Verify that GET /api/v1/health returns 200 and development diagnostics."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["environment"] == "test"
    assert data["database"]["status"] == "connected"
    assert "type" in data["database"]


@pytest.mark.asyncio
async def test_error_handling_not_found(client: AsyncClient):
    """Verify consistent JSON error response on 404."""
    response = await client.get("/api/v1/nonexistent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]


def test_production_database_config_enforcement():
    """Verify that production fails loudly if DATABASE_URL is missing or uses SQLite."""
    # Test missing in production
    settings_missing = Settings(APP_ENV="production", DATABASE_URL=None)
    with pytest.raises(RuntimeError, match="Production configuration error"):
        _ = settings_missing.effective_database_url

    # Test SQLite in production
    settings_sqlite = Settings(APP_ENV="production", DATABASE_URL="sqlite+aiosqlite:///./prod.db")
    with pytest.raises(RuntimeError, match="SQLite is not permitted in production"):
        _ = settings_sqlite.effective_database_url

    # Test valid PostgreSQL in production
    settings_pg = Settings(
        APP_ENV="production", DATABASE_URL="postgresql+psycopg://user:pass@dbhost:5432/proddb"
    )
    assert settings_pg.effective_database_url == "postgresql+psycopg://user:pass@dbhost:5432/proddb"
