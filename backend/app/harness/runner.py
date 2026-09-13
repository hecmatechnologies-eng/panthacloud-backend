"""``AgentRunner`` — the seam between the harness and the agent framework (ADR-001, FR-072).

The harness depends on this Protocol; the Pydantic AI implementation lives behind it in
``app/llm/adapters/``. Nothing in ``app/agents/``, ``app/harness/`` or ``app/runtime/`` imports an
agent framework or a provider SDK. Swapping frameworks is one adapter file, not a rewrite.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from app.agents.base import AgentDefinition
from app.harness.context import ExecutionContext


class StructuredOutputError(Exception):
    """The model did not return output matching the agent's schema, after the framework's retries.

    A failed step, not a best-effort string (AGENT-ARCHITECTURE §14).
    """


class AgentRunnerError(Exception):
    """The runner could not complete the call — a provider, configuration or transport failure."""


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    output: BaseModel | None
    text: str | None
    input_tokens: int
    output_tokens: int
    provider: str
    model_id: str
    model_version_reported: str | None


# Called with the result so the harness can meter the call through the model gateway (FR-073).
UsageRecorder = Callable[[AgentRunResult], Awaitable[None]]


class AgentRunner(Protocol):
    async def run(
        self,
        definition: AgentDefinition,
        context: ExecutionContext,
        *,
        prompt: str,
        usage_recorder: UsageRecorder | None = None,
    ) -> AgentRunResult: ...
