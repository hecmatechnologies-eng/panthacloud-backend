"""Stopping a run for reasons other than a budget breach (OWASP ASI08, ASI10).

``BudgetTracker`` already stops a run that costs too much or takes too long. These are the
other two reasons, and both were previously impossible:

- **Operator halt** — a human has stopped execution, globally or for one organisation. The
  state lives outside this module, because ``app/harness/`` may not import anything that
  touches Redis or the database. Callers pass a ``halt_check`` callable instead, the same way
  ``runner`` and ``tool_gateway`` are already injected.

- **Circuit breaker** — the run is failing repeatedly. ASI08 describes this as a cascade in
  progress: one bad decision feeding the next. Counting consecutive failures and stopping is
  the cheapest available bound, and it needs no baseline of "normal" behaviour to be useful.

Nothing here performs I/O. That is deliberate: the harness depends on abstractions, and this
keeps it testable without a live Redis.
"""

from __future__ import annotations


class RunHaltedError(Exception):
    """An operator has halted this run. Terminal, and never retried."""


class CircuitBreakerOpen(Exception):
    """The run failed too many times in a row. Terminal, and never retried."""


class CircuitBreaker:
    """Stops a run after ``threshold`` consecutive tool failures.

    Consecutive, not cumulative: a run that fails once, succeeds, then fails again is making
    progress and must not be stopped. Only an unbroken run of failures indicates the agent is
    stuck rather than unlucky.
    """

    def __init__(self, threshold: int) -> None:
        if threshold < 1:
            raise ValueError("threshold must be at least 1")
        self._threshold = threshold
        self._consecutive = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive

    def record_success(self) -> None:
        self._consecutive = 0

    def record_failure(self) -> None:
        """Count one failure, and stop the run once the threshold is reached."""
        self._consecutive += 1
        if self._consecutive >= self._threshold:
            raise CircuitBreakerOpen(
                f"Run failed {self._consecutive} consecutive tool calls; "
                f"stopping at threshold {self._threshold}."
            )