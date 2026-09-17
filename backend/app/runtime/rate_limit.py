"""Rate limiting for the runtime plane (FR-113).

Supports atomic distributed sliding-window rate limiting via Redis (for multi-replica container
deployments), with automatic and transparent fallback to in-memory fixed-window rate limiting when
Redis is unconfigured (local SQLite development or unit tests).

Atomic Redis evaluation uses a Lua script over Sorted Sets (ZSET), ensuring zero race conditions
and sub-millisecond evaluation across distributed application workers.
"""

import logging
import math
import time
import uuid

import redis

logger = logging.getLogger("fussion.rate_limit")

# Bound on tracked buckets in memory when Redis is absent.
_MAX_TRACKED_BUCKETS = 10_000

# Atomic Redis sliding-window script using Sorted Set (ZSET)
# KEYS[1]: rate limit key
# ARGV[1]: current timestamp (float/int)
# ARGV[2]: window in seconds
# ARGV[3]: max allowed requests
# ARGV[4]: unique hit member id
_REDIS_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)
local current_count = redis.call('ZCARD', key)

if current_count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = window
    if oldest and #oldest >= 2 then
        retry_after = math.ceil(tonumber(oldest[2]) + window - now)
    end
    if retry_after < 1 then retry_after = 1 end
    return {0, retry_after}
else
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, window + 5)
    return {1, 0}
end
"""


class RateLimitExceeded(Exception):
    """The caller has exceeded a scope's allowance for the current window."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded.")
        self.retry_after = max(1, retry_after)


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    async def check(
        self,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        """Record one hit for ``(scope, key)`` or raise ``RateLimitExceeded``.

        If Redis is configured and available, uses atomic Redis sliding-window algorithm.
        Otherwise, seamlessly falls back to in-memory tracking.
        """
        if limit <= 0:
            return

        from app.core.redis import get_redis

        redis_client = get_redis()
        if redis_client is not None:
            try:
                await self._check_redis(redis_client, scope, key, limit, window_seconds, now)
                return
            except (redis.RedisError, OSError, ConnectionError, RuntimeError) as exc:
                logger.warning("Redis rate limiter failed, falling back to memory: %s", exc)

        self._check_memory(scope, key, limit, window_seconds, now)

    async def _check_redis(
        self,
        redis_client: redis.asyncio.Redis,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        current_ts = time.time() if now is None else now
        redis_key = f"fussion:ratelimit:{scope}:{key}"
        member = f"{current_ts}:{uuid.uuid4().hex[:8]}"

        result = await redis_client.eval(
            _REDIS_SLIDING_WINDOW_LUA,
            1,
            redis_key,
            str(current_ts),
            str(window_seconds),
            str(limit),
            member,
        )

        allowed = int(result[0])
        retry_after = int(result[1])
        if allowed == 0:
            raise RateLimitExceeded(retry_after=retry_after)

    def check_sync(
        self,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        """Synchronous in-memory rate check for testing and standalone fallbacks."""
        if limit <= 0:
            return
        self._check_memory(scope, key, limit, window_seconds, now)

    def _check_memory(
        self,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        now_ts = time.monotonic() if now is None else now
        bucket = (scope, key)
        start, count = self._windows.get(bucket, (now_ts, 0))
        if now_ts - start >= window_seconds:
            start, count = now_ts, 0
        if count >= limit:
            raise RateLimitExceeded(retry_after=math.ceil(start + window_seconds - now_ts))
        if len(self._windows) >= _MAX_TRACKED_BUCKETS:
            self._prune(now_ts, window_seconds)
            if len(self._windows) >= _MAX_TRACKED_BUCKETS:
                del self._windows[min(self._windows, key=lambda b: self._windows[b][0])]
        self._windows[bucket] = (start, count + 1)

    def _prune(self, now: float, window_seconds: int) -> None:
        self._windows = {
            bucket: window
            for bucket, window in self._windows.items()
            if now - window[0] < window_seconds
        }

    def reset(self) -> None:
        """Reset in-memory rate limit windows."""
        self._windows.clear()


rate_limiter = RateLimiter()
