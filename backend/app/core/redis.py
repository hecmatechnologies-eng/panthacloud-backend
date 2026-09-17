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
