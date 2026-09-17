"""Tests for distributed and in-memory rate limiting."""

from unittest.mock import AsyncMock

import pytest

from app.runtime.rate_limit import RateLimiter, RateLimitExceeded


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter = RateLimiter()
    limiter.reset()
    yield limiter
    limiter.reset()


@pytest.mark.asyncio
async def test_memory_rate_limiter_allows_under_limit():
    limiter = RateLimiter()
    # Limit: 3 requests per 10-second window
    await limiter.check("test_scope", "key_1", limit=3, window_seconds=10)
    await limiter.check("test_scope", "key_1", limit=3, window_seconds=10)
    await limiter.check("test_scope", "key_1", limit=3, window_seconds=10)


@pytest.mark.asyncio
async def test_memory_rate_limiter_blocks_when_exceeded():
    limiter = RateLimiter()
    await limiter.check("test_scope", "key_2", limit=2, window_seconds=10)
    await limiter.check("test_scope", "key_2", limit=2, window_seconds=10)

    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter.check("test_scope", "key_2", limit=2, window_seconds=10)

    assert exc_info.value.retry_after > 0


@pytest.mark.asyncio
async def test_memory_rate_limiter_slides_window():
    limiter = RateLimiter()
    base_time = 1000.0

    # Fill allowance at base_time
    await limiter.check("test_scope", "key_3", limit=1, window_seconds=5, now=base_time)
    with pytest.raises(RateLimitExceeded):
        await limiter.check("test_scope", "key_3", limit=1, window_seconds=5, now=base_time + 1.0)

    # After window expires, should allow again
    await limiter.check("test_scope", "key_3", limit=1, window_seconds=5, now=base_time + 6.0)


@pytest.mark.asyncio
async def test_disabled_limit_never_raises():
    limiter = RateLimiter()
    # 0 or negative limit disables checking
    await limiter.check("test_scope", "key_disabled", limit=0, window_seconds=10)
    await limiter.check("test_scope", "key_disabled", limit=-1, window_seconds=10)


def test_check_sync_functions_identically():
    limiter = RateLimiter()
    limiter.check_sync("test_scope", "key_sync", limit=1, window_seconds=10)
    with pytest.raises(RateLimitExceeded):
        limiter.check_sync("test_scope", "key_sync", limit=1, window_seconds=10)


@pytest.mark.asyncio
async def test_redis_sliding_window_allowed():
    limiter = RateLimiter()
    mock_redis = AsyncMock()
    # Mock Lua script eval returning [1, 0] (allowed)
    mock_redis.eval.return_value = [1, 0]

    await limiter._check_redis(mock_redis, "test_scope", "client_1", limit=10, window_seconds=60)
    assert mock_redis.eval.called
    args = mock_redis.eval.call_args[0]
    assert args[2] == "fussion:ratelimit:test_scope:client_1"


@pytest.mark.asyncio
async def test_redis_sliding_window_exceeded():
    limiter = RateLimiter()
    mock_redis = AsyncMock()
    # Mock Lua script eval returning [0, 42] (exceeded, retry after 42s)
    mock_redis.eval.return_value = [0, 42]

    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter._check_redis(mock_redis, "test_scope", "client_2", limit=5, window_seconds=60)

    assert exc_info.value.retry_after == 42
