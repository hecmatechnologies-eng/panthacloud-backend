"""Async Redis connection pool and pub/sub infrastructure for Fussion.

Manages connection pooling, real-time audit event streaming, and background task queues.
Designed with graceful degradation: if Redis is unconfigured or unreachable, all operations
fail safely without interrupting core platform services.
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings

logger = logging.getLogger("fussion.redis")

_pool: ConnectionPool | None = None
_client: redis.Redis | None = None

EVENT_CHANNEL_PREFIX = "fussion:events"


def project_event_channel(project_id: uuid.UUID | str) -> str:
    """Standardized Redis channel name for project-level studio events."""
    return f"{EVENT_CHANNEL_PREFIX}:{project_id}"


def get_redis() -> redis.Redis | None:
    """Return an active async Redis client instance, or None if unconfigured.

    Reuses a global ConnectionPool for high-throughput concurrency.
    """
    global _pool, _client

    url = settings.effective_redis_url
    if not url:
        return None

    if _client is None:
        try:
            _pool = ConnectionPool.from_url(
                url,
                max_connections=50,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            _client = redis.Redis(connection_pool=_pool)
            logger.info("Initialized async Redis connection pool")
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.warning("Failed to initialize Redis client: %s", exc)
            return None

    return _client


async def close_redis() -> None:
    """Close connection pool and client during application teardown."""
    global _pool, _client
    if _client is not None:
        try:
            await _client.aclose()
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.debug("Error closing Redis client: %s", exc)
        _client = None

    if _pool is not None:
        try:
            await _pool.disconnect()
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.debug("Error disconnecting Redis pool: %s", exc)
        _pool = None


async def publish_audit_event(
    event: Any,
    project_id: uuid.UUID | str | None = None,
) -> bool:
    """Publish an AuditEvent payload to its project's Redis Pub/Sub channel.

    Returns True if successfully published to Redis, or False if skipped/failed.
    """
    target_project_id = project_id or getattr(event, "project_id", None)
    if target_project_id is None:
        return False

    client = get_redis()
    if client is None:
        return False

    channel = project_event_channel(target_project_id)
    payload = {
        "id": str(getattr(event, "id", "")),
        "event_type": getattr(event, "event_type", ""),
        "payload": getattr(event, "payload", {}),
        "created_at": getattr(event, "created_at", "").isoformat()
        if hasattr(getattr(event, "created_at", None), "isoformat")
        else str(getattr(event, "created_at", "")),
    }

    try:
        await client.publish(channel, json.dumps(payload))
        return True
    except (redis.RedisError, OSError, ValueError) as exc:
        logger.warning("Failed to publish audit event to channel '%s': %s", channel, exc)
        return False


async def subscribe_project_events(
    project_id: uuid.UUID | str,
) -> AsyncGenerator[dict[str, Any]]:
    """Async generator yielding deserialized event dictionaries from a project channel."""
    client = get_redis()
    if client is None:
        return

    channel = project_event_channel(project_id)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    yield data
                except (json.JSONDecodeError, TypeError):
                    continue
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.debug("Error closing pubsub subscriber: %s", exc)


# In-memory fallback sets for token revocation when Redis is unconfigured (testing/local dev)
_local_blacklist: set[str] = set()
_local_user_revoked: dict[str, int] = {}

TOKEN_BLACKLIST_PREFIX = "fussion:token:blacklist"
USER_REVOKED_PREFIX = "fussion:user:revoked_before"


async def blacklist_token(jti: str, ttl_seconds: int = 86400) -> bool:
    """Add a JWT ID (jti) to the revocation blacklist with a given TTL.

    Uses Redis if available, or falls back to in-memory set for test environments.
    """
    client = get_redis()
    if client is not None:
        try:
            key = f"{TOKEN_BLACKLIST_PREFIX}:{jti}"
            await client.set(key, "1", ex=max(1, ttl_seconds))
            return True
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.warning("Failed to blacklist token in Redis: %s", exc)

    _local_blacklist.add(jti)
    return True


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a JWT ID (jti) has been revoked."""
    client = get_redis()
    if client is not None:
        try:
            key = f"{TOKEN_BLACKLIST_PREFIX}:{jti}"
            exists = await client.exists(key)
            return bool(exists)
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.warning("Failed to check token blacklist in Redis: %s", exc)

    return jti in _local_blacklist


async def set_user_revoked_before(
    user_id: uuid.UUID | str,
    timestamp: int,
    ttl_seconds: int = 86400,
) -> bool:
    """Set the timestamp before which all issued tokens for a user are considered revoked."""
    u_id = str(user_id)
    client = get_redis()
    if client is not None:
        try:
            key = f"{USER_REVOKED_PREFIX}:{u_id}"
            await client.set(key, str(timestamp), ex=max(1, ttl_seconds))
            return True
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.warning("Failed to set user revocation in Redis: %s", exc)

    _local_user_revoked[u_id] = timestamp
    return True


async def is_user_revoked(user_id: uuid.UUID | str, issued_at: int) -> bool:
    """Check if a token was issued before the user's latest revocation timestamp."""
    u_id = str(user_id)
    client = get_redis()
    if client is not None:
        try:
            key = f"{USER_REVOKED_PREFIX}:{u_id}"
            val = await client.get(key)
            if val is not None:
                return issued_at < int(val)
        except (redis.RedisError, OSError, ValueError) as exc:
            logger.warning("Failed to check user revocation in Redis: %s", exc)

    revoked_before = _local_user_revoked.get(u_id)
    if revoked_before is not None:
        return issued_at < revoked_before
    return False


def reset_token_blacklist() -> None:
    """Reset the in-memory token blacklist (for unit testing)."""
    _local_blacklist.clear()
    _local_user_revoked.clear()


async def check_redis_connectivity() -> tuple[bool, float | None]:
    """Check connectivity to Redis with ping latency.

    Returns:
        (is_healthy, latency_ms)
    """
    import time

    client = get_redis()
    if client is None:
        return False, None
    try:
        start = time.perf_counter()
        res = await client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return bool(res), latency_ms
    except (redis.RedisError, OSError, ValueError) as exc:
        logger.warning("Redis health check failed: %s", exc)
        return False, None
