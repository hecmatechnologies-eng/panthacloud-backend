import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger("fussion.database")


class Base(DeclarativeBase):
    pass


# Global engine and sessionmaker references
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_url = settings.effective_database_url
        logger.info("Initializing database engine with %s", db_url.split("@")[-1])
        _engine = create_async_engine(db_url, echo=False, future=True, **_pool_options(db_url))
    return _engine


def _pool_options(db_url: str) -> dict[str, object]:
    """Connection-pool settings for a server database; none for SQLite.

    The defaults (``pool_size=5``, ``max_overflow=10``, no pre-ping) are tuned for a database that
    keeps its connections. A managed Postgres does not: the platform's proxy and PostgreSQL's own
    ``idle_session_timeout`` both close idle connections, and without ``pool_pre_ping`` the next
    request after a quiet period fails with *"server closed the connection unexpectedly"* — the kind
    of error that looks like an application bug and is not.

    SQLite is excluded deliberately: it is the development and test database, it is single-writer,
    and its dialect does not accept these arguments at all.
    """
    if db_url.startswith("sqlite"):
        return {}
    return {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 20,
        "max_overflow": 20,
        "pool_timeout": 30,
    }


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Dependency for obtaining an asynchronous database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connectivity() -> tuple[bool, str, float | None]:
    """
    Checks database reachability by executing a lightweight probe query.
    Returns: (is_healthy, dialect_name, latency_ms)
    """
    start_time = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start_time) * 1000.0
        dialect = engine.dialect.name
        return True, dialect, round(latency, 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("Database connectivity check failed: %s", e)
        return False, "unknown", None


async def close_database_connections() -> None:
    """Disposes engine connections during application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
