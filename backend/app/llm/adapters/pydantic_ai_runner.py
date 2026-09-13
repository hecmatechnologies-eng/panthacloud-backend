"""Pydantic AI adapter (ADR-001, FR-125).

The only module that imports ``pydantic_ai``. It builds an ``Agent`` from a Fussion
``AgentDefinition``, runs it, and returns the validated structured output plus token usage. Usage is
handed to a recorder so the harness can meter it through the model gateway (FR-073). The vendor
model object is constructed here from settings — nowhere else knows a provider SDK exists.
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentDefinition
from app.core.config import Settings, settings
from app.harness.context import ExecutionContext
from app.harness.runner import (
    AgentRunnerError,
    AgentRunResult,
    StructuredOutputError,
    UsageRecorder,
)
from app.llm.factory import resolve_provider_config
from app.llm.gateway import ModelGateway


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
        usage_recorder: UsageRecorder | None = None,
    ) -> AgentRunResult:
        from pydantic_ai import Agent
        from pydantic_ai.exceptions import (
            ContentFilterError,
            IncompleteToolCall,
            UnexpectedModelBehavior,
        )

        agent = Agent(
            self._model or _build_model(settings),
            instructions=definition.instructions,
            output_type=definition.output_schema or str,
        )
        try:
            result = await agent.run(prompt)
        except (ContentFilterError, IncompleteToolCall) as exc:
            # These subclass UnexpectedModelBehavior but are provider failures, not bad output.
            raise AgentRunnerError(str(exc)) from exc
        except UnexpectedModelBehavior as exc:
            raise StructuredOutputError(str(exc)) from exc
        except Exception as exc:
            raise AgentRunnerError(str(exc)) from exc

        output = result.output
        run_result = AgentRunResult(
            output=output if isinstance(output, BaseModel) else None,
            text=output if isinstance(output, str) else None,
            input_tokens=result.usage.input_tokens or 0,
            output_tokens=result.usage.output_tokens or 0,
            provider=settings.MODEL_PROVIDER,
            model_id=settings.MODEL_ID,
            model_version_reported=getattr(result.response, "model_name", None),
        )
        if usage_recorder is not None:
            await usage_recorder(run_result)
        return run_result


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
        )

    return record
