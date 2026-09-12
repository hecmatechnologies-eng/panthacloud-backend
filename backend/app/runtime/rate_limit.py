"""In-process rate limiting for the runtime plane (FR-113).

Per-process, in-memory, fixed-window. That is honest for a single-process MVP and wrong the moment
there is more than one worker — each replica would keep its own counters, so the effective limit
multiplies by the replica count. A Redis-backed implementation is the trigger-named replacement
(CLAUDE.md §6, Avoid Premature Optimization): no Redis exists in the MVP.

The check is synchronous and holds no await, so on a single event loop it is atomic with respect
to other requests.
"""

import math
import time

# Bound on tracked buckets. Sustained distinct-key traffic can otherwise grow the map for the
# length of a window; at the cap the oldest window is evicted so memory stays bounded.
_MAX_TRACKED_BUCKETS = 10_000


class RateLimitExceeded(Exception):
    """The caller has exceeded a scope's allowance for the current window."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded.")
        self.retry_after = max(1, retry_after)


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def check(
        self,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        """Record one hit for ``(scope, key)`` or raise ``RateLimitExceeded``.

        A non-positive ``limit`` disables the scope. ``now`` is injectable for deterministic tests.
        """
        if limit <= 0:
            return
        now = time.monotonic() if now is None else now
        bucket = (scope, key)
        start, count = self._windows.get(bucket, (now, 0))
        if now - start >= window_seconds:
            start, count = now, 0
        if count >= limit:
            raise RateLimitExceeded(retry_after=math.ceil(start + window_seconds - now))
        if len(self._windows) >= _MAX_TRACKED_BUCKETS:
            self._prune(now, window_seconds)
            if len(self._windows) >= _MAX_TRACKED_BUCKETS:
                # Still full (every tracked key is inside its window): evict the oldest so memory
                # is bounded even under sustained distinct-key traffic.
                del self._windows[min(self._windows, key=lambda bucket: self._windows[bucket][0])]
        self._windows[bucket] = (start, count + 1)

    def _prune(self, now: float, window_seconds: int) -> None:
        self._windows = {
            bucket: window
            for bucket, window in self._windows.items()
            if now - window[0] < window_seconds
        }

    def reset(self) -> None:
        self._windows.clear()


rate_limiter = RateLimiter()
