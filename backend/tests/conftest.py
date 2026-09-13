import os
from collections.abc import AsyncGenerator
from secrets import token_urlsafe

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

# Enforce test environment before importing app
os.environ["APP_ENV"] = "test"
os.environ["FALLBACK_SQLITE_URL"] = "sqlite+aiosqlite:///./test_fussion.db"

# Supply the test run's own keys, so no test reads or writes a developer's generated
# .dev-secrets.json (app/core/dev_secrets.py). Fresh per run, and never a value from source.
# Assigned, not setdefault: an exported SECRET_ENCRYPTION_KEY in the developer's shell — which
# CLAUDE.md §3.2 suggests for continuity with the old key — must not become what the suite uses.
os.environ["JWT_SECRET_KEY"] = token_urlsafe(48)
os.environ["SECRET_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")

# Tests must never call a paid embedding API. The deterministic provider is lexical but
# deterministic and offline; production uses the configured real provider (app/core/config.py).
os.environ["EMBEDDING_PROVIDER"] = "deterministic"
os.environ["EMBEDDING_DIMENSION"] = "384"

import app.models
from app.core.database import Base, get_engine
from app.main import app

# Created once per test run, then reused. Recreating the whole schema per test (create_all +
# drop_all) dominated the suite's runtime as the model count grew; deleting rows between tests is
# far cheaper and gives each test the same isolation it expected: it starts with no rows.
_schema_initialized = False


async def _prepare_schema_once() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    engine = get_engine()
    async with engine.begin() as conn:
        # Drop first so a schema left by a previous run is never reused stale.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    _schema_initialized = True


async def _clear_all_rows() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        # Children before parents: `sorted_tables` is parent-first, so reverse it.
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture(autouse=True)
async def prepare_database():
    """Create the schema once, then give each test an empty database."""
    await _prepare_schema_once()
    yield
    await _clear_all_rows()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
