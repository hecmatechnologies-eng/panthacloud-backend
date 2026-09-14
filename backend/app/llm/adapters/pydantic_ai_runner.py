"""Pydantic AI adapter (ADR-001, FR-125).

The only module that imports ``pydantic_ai``. It builds an ``Agent`` from a Fussion
``AgentDefinition``, exposes the agent's tools, runs it, and returns the validated structured output
plus token usage. Usage is handed to a recorder so the harness can meter it through the model
gateway (FR-073). The vendor model object is constructed here from settings — nowhere else knows a
provider SDK exists.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentDefinition
from app.core.config import Settings, settings
from app.harness.context import ExecutionContext
from app.harness.runner import (
    AgentBudgetExceededError,
    AgentRunnerError,
    AgentRunResult,
    HarnessError,
    StructuredOutputError,
    ToolExecutor,
    ToolSpec,
    UsageRecorder,
)
from app.llm.factory import resolve_provider_config
from app.llm.gateway import ModelGateway

logger = logging.getLogger("fussion.llm.adapters")


class PydanticAIAgentRunner:
    def __init__(self, model: object | None = None) -> None:
        # A model is injected only by tests (pydantic_ai's TestModel/FunctionModel); production
        # builds it from settings so no API key is needed to construct the runner.
        self._model = model

    async def run(
        self,
        definition: AgentDefinition,
        context: ExecutionContext,
        *,
        prompt: str,
        tools: Sequence[ToolSpec] = (),
        tool_executor: ToolExecutor | None = None,
        usage_recorder: UsageRecorder | None = None,
    ) -> AgentRunResult:
        from pydantic_ai import Agent
        from pydantic_ai.exceptions import (
            ContentFilterError,
            IncompleteToolCall,
            UnexpectedModelBehavior,
            UsageLimitExceeded,
        )
        from pydantic_ai.usage import RunUsage, UsageLimits

        agent = Agent(
            self._model or _build_model(settings),
            instructions=definition.instructions,
            output_type=definition.output_schema or str,
            tools=_build_tools(tools, tool_executor),
        )
        limits = UsageLimits(
            tool_calls_limit=definition.budget.tool_calls,
            total_tokens_limit=definition.budget.tokens,
        )
        # Accumulates as calls happen, so usage is not lost when the run fails mid-loop.
        usage = RunUsage()
        try:
            result = await agent.run(prompt, usage_limits=limits, usage=usage)
        except HarnessError:
            # A policy denial or budget breach raised inside a tool must reach the harness intact.
            await _report_partial_usage(usage, usage_recorder)
            raise
        except UsageLimitExceeded as exc:
            await _report_partial_usage(usage, usage_recorder)
            raise AgentBudgetExceededError(str(exc)) from exc
        except (ContentFilterError, IncompleteToolCall) as exc:
            # These subclass UnexpectedModelBehavior but are provider failures, not bad output.
            await _report_partial_usage(usage, usage_recorder)
            raise AgentRunnerError(str(exc)) from exc
        except UnexpectedModelBehavior as exc:
            await _report_partial_usage(usage, usage_recorder)
            raise StructuredOutputError(str(exc)) from exc
        except asyncio.CancelledError:
            # A wall-clock timeout or shutdown cancelled the run: report what was spent first.
            await _report_partial_usage(usage, usage_recorder)
            raise
        except Exception as exc:
            await _report_partial_usage(usage, usage_recorder)
            raise AgentRunnerError(str(exc)) from exc

        output = result.output
        run_result = AgentRunResult(
            output=output if isinstance(output, BaseModel) else None,
            text=output if isinstance(output, str) else None,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            provider=settings.MODEL_PROVIDER,
            model_id=settings.MODEL_ID,
            model_version_reported=getattr(result.response, "model_name", None),
        )
        if usage_recorder is not None:
            await usage_recorder(run_result)
        return run_result


async def _report_partial_usage(
    usage: object, recorder: UsageRecorder | None
) -> None:
    """Report what was spent before a failure, so the ledger and budget see it (FR-073)."""
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    if recorder is None or not (input_tokens or output_tokens):
        return
    try:
        await recorder(
            AgentRunResult(
                output=None,
                text=None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider=settings.MODEL_PROVIDER,
                model_id=settings.MODEL_ID,
                model_version_reported=None,
            )
        )
    except Exception:
        # Never mask the original failure; the ledger write is best-effort here.
        logger.warning("Could not record partial usage for a failed agent run.", exc_info=True)


def _build_tools(specs: Sequence[ToolSpec], executor: ToolExecutor | None) -> list[Any]:
    if not specs:
        return []
    if executor is None:
        raise AgentRunnerError("Tools were provided without a tool executor.")
    from pydantic_ai.tools import Tool

    built = []
    for spec in specs:

        async def call(_executor: ToolExecutor = executor, _name: str = spec.name, **kwargs: Any) -> str:
            return await _executor(_name, kwargs)

        built.append(
            Tool.from_schema(
                call, spec.name, spec.description, spec.input_schema.model_json_schema()
            )
        )
    return built


def _build_model(config: Settings) -> object:
    if not config.MODEL_API_KEY:
        # Fail fast rather than attempt a call on an empty credential (CLAUDE.md §4.10).
        raise AgentRunnerError("No model API key is configured.")
    provider = resolve_provider_config(config)
    if provider.kind == "gemini":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(provider.model_id, provider=GoogleProvider(api_key=provider.api_key))

    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    return OpenAIChatModel(
        provider.model_id,
        provider=OpenAIProvider(base_url=provider.base_url or "", api_key=provider.api_key),
    )


def gateway_usage_recorder(
    gateway: ModelGateway, db: AsyncSession, context: ExecutionContext, *, latency_ms: int = 0
) -> UsageRecorder:
    """A ``UsageRecorder`` that meters an agent call through the model gateway (FR-073)."""

    async def record(result: AgentRunResult) -> None:
        await gateway.record_external_usage(
            db,
            organization_id=context.organization_id,
            provider=result.provider,
            model=result.model_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            project_id=context.project_id,
            integration_id=context.integration_id,
        )

    return record
