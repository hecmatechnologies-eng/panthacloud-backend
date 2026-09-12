"""Declarative agent contracts (FR-046).

An ``AgentDefinition`` is data. It names the capabilities the harness must grant, the tools it may
call, the schema its output is parsed into, and the budget it may consume. Nothing here reaches the
database, the network, or a domain service — that is the harness's job, through the tool gateway.
"""

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class Budget:
    """Per-run ceilings, enforced by the harness (FR-053)."""

    tool_calls: int
    tokens: int
    seconds: int
    cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    version: str
    instructions: str
    capabilities: frozenset[str]
    tools: tuple[str, ...]
    output_schema: type[BaseModel] | None
    budget: Budget
