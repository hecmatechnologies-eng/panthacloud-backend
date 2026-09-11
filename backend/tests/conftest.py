import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

# Enforce test environment before importing app
os.environ["APP_ENV"] = "test"
os.environ["FALLBACK_SQLITE_URL"] = "sqlite+aiosqlite:///./test_fussion.db"

import app.models
from app.core.database import Base, get_engine
from app.main import app


@pytest.fixture(autouse=True)
async def prepare_database():
    """Ensure database schema is cleanly initialized for tests."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
