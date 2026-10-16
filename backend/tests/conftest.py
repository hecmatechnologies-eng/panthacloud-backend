import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from secrets import token_urlsafe

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

# Enforce test environment before importing app
os.environ["APP_ENV"] = "test"

# One database file per process, in the temp directory.
#
# A fixed path made two concurrent pytest runs share it, and `_clear_all_rows` then deleted the
# other run's users mid-test — surfacing as baffling 401s from a token that had worked one request
# earlier. Both variables are set so the file is used whether or not the developer's `.env` names a
# SQLite database of its own (config.effective_database_url prefers DATABASE_URL when it is SQLite).
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"fussion-test-{os.getpid()}.db"
_TEST_DB_URL = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["FALLBACK_SQLITE_URL"] = _TEST_DB_URL

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

# The email reply delay exists so that an automated reply does not look machine-generated. That is
# a question about a real mailbox's spam filter and has no meaning in a test, but the wait is real
# wall-clock time: left at the shipped default of 90 seconds, every email webhook test sleeps for a
# minute and a half and the suite appears to hang. Set for the whole run rather than per-test so a
# future test cannot reintroduce it by omission.
os.environ["EMAIL_REPLY_DELAY_SECONDS"] = "0"

# The autonomous coding agent is off by default in the suite. It was previously disabled by an
# `APP_ENV != "test"` check buried in the pipeline, which also meant the wiring around it was
# never executed. Tests that need it force it on explicitly with a stubbed runner.
os.environ["ENABLE_CODING_AGENT"] = "false"

from sqlalchemy.ext.asyncio import AsyncSession

import app.models
from app.core.database import Base, get_engine, get_session_factory
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


@pytest.fixture(scope="session", autouse=True)
def _remove_this_process_database():
    """Drop this process's database file at the end. Best effort: Windows holds open handles."""
    yield
    try:
        _TEST_DB_PATH.unlink(missing_ok=True)
    except OSError:
        pass  # the OS clears the temp directory; a leftover file is harmless


@pytest.fixture(autouse=True)
async def prepare_database():
    """Create the schema once, then give each test an empty database."""
    await _prepare_schema_once()
    yield
    await _clear_all_rows()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
