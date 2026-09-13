"""``AgentRunner`` — the seam between the harness and the agent framework (ADR-001, FR-072).

The harness depends on this Protocol; the Pydantic AI implementation lives behind it in
``app/llm/adapters/``. Nothing in ``app/agents/``, ``app/harness/`` or ``app/runtime/`` imports an
agent framework or a provider SDK. Swapping frameworks is one adapter file, not a rewrite.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.base import AgentDefinition
from app.harness.context import ExecutionContext


class StructuredOutputError(Exception):
    """The model did not return output matching the agent's schema, after the framework's retries.

    A failed step, not a best-effort string (AGENT-ARCHITECTURE §14).
    """


class HarnessError(Exception):
    """Base for errors the harness raises from inside tool execution.

    These must reach the harness loop unchanged: an agent framework must never rewrite a policy
    denial or a budget breach into a generic provider failure (FR-066, FR-100).
    """


class ToolDeniedError(HarnessError):
    """A tool call was refused on policy grounds; the run stops rather than let the model retry
    its way around authorization (FR-066)."""


class AgentRunnerError(Exception):
    """The runner could not complete the call — a provider, configuration or transport failure."""


class AgentBudgetExceededError(Exception):
    """The agent framework stopped the run because a declared usage limit was reached (FR-053)."""


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    output: BaseModel | None
    text: str | None
    input_tokens: int
    output_tokens: int
    provider: str
    model_id: str
    model_version_reported: str | None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool exposed to the model: enough for the framework to build its schema."""

    name: str
    description: str
    input_schema: type[BaseModel]


# Called with (tool_name, validated-or-raw arguments) and returns a model-readable observation.
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]

# Called with the result so the harness can meter the call through the model gateway (FR-073).
UsageRecorder = Callable[[AgentRunResult], Awaitable[None]]


class AgentRunner(Protocol):
    async def run(
        self,
        definition: AgentDefinition,
        context: ExecutionContext,
        *,
        prompt: str,
        tools: Sequence[ToolSpec] = (),
        tool_executor: ToolExecutor | None = None,
        usage_recorder: UsageRecorder | None = None,
    ) -> AgentRunResult: ...
