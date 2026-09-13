"""Per-run budget enforcement (FR-053).

A run declares ceilings on tool calls, tokens, wall-clock seconds and cost. The harness checks them
as the run proceeds and terminates the moment one is breached — an uncapped run is an unbounded
cost event.
"""

import time
from dataclasses import dataclass, field
from decimal import Decimal

from app.agents.base import Budget
from app.harness.runner import HarnessError


class RunBudgetExceeded(HarnessError):
    """A run exceeded one of its declared budgets and must terminate."""

    def __init__(self, limit: str) -> None:
        super().__init__(f"Run budget exceeded: {limit}.")
        self.limit = limit


@dataclass
class BudgetTracker:
    budget: Budget
    tool_calls: int = 0
    tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    started_at: float = field(default_factory=time.monotonic)

    def record_tool_call(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.budget.tool_calls:
            raise RunBudgetExceeded("tool_calls")

    def record_usage(self, *, input_tokens: int, output_tokens: int, cost_usd: Decimal) -> None:
        self.tokens += input_tokens + output_tokens
        self.cost_usd += cost_usd
        if self.tokens > self.budget.tokens:
            raise RunBudgetExceeded("tokens")
        if self.cost_usd > self.budget.cost_usd:
            raise RunBudgetExceeded("cost_usd")

    def check_wall_clock(self) -> None:
        if time.monotonic() - self.started_at > self.budget.seconds:
            raise RunBudgetExceeded("seconds")
