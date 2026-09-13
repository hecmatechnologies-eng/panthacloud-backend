"""The one harness loop (FR-050, FR-053, FR-054).

Orchestrates a single agent execution: build the run from the trusted context, expose the agent's
declared tools through the gateway, meter the call, enforce the run budget, and finish the record.
The model loop itself is the framework's, behind ``AgentRunner``; the harness owns everything the
model must not — tenancy, tool authorization, budget and audit.
"""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentDefinition
from app.core.config import settings
from app.harness.budget import BudgetTracker, RunBudgetExceeded
from app.harness.context import ExecutionContext
from app.harness.run import finish_agent_run, record_run_metadata, start_agent_run
from app.harness.runner import (
    AgentBudgetExceededError,
    AgentRunner,
    AgentRunnerError,
    AgentRunResult,
    StructuredOutputError,
    ToolDeniedError,
    ToolSpec,
)
from app.llm.gateway import BudgetExceededError, ModelGateway
from app.llm.pricing import estimate_cost_usd
from app.models.agent_run import AgentRun, AgentRunStatus, FailureClass
from app.tools.base import ToolResult
from app.tools.gateway import ApprovedPlan, ToolGateway
from app.tools.registry import ToolRegistry


async def run_agent(
    db: AsyncSession,
    *,
    context: ExecutionContext,
    definition: AgentDefinition,
    prompt: str,
    runner: AgentRunner,
    gateway: ModelGateway,
    tool_gateway: ToolGateway,
    registry: ToolRegistry,
    approved_plan: ApprovedPlan | None = None,
    on_result: Callable[[AgentRunResult], Awaitable[None]] | None = None,
    skill_versions: dict[str, str] | None = None,
) -> AgentRun:
    run = await start_agent_run(db, context, definition)
    # Bind the run id onto the context so tool calls and the gateway can prove they belong to it.
    context = context.bind_run(run.id)
    budget = BudgetTracker(definition.budget)

    try:
        # Reproducibility is recorded up front, so a failed run is still reconstructible (FR-089).
        await record_run_metadata(
            db,
            run,
            prompt_hash=_prompt_hash(prompt),
            model_id=settings.MODEL_ID,
            skill_versions=skill_versions,
        )
        # Refuse before the call if the organization is already over its spend budget (FR-074).
        await gateway.ensure_budget(db, context.organization_id)
        specs = _tool_specs(definition, registry)

        async def execute_tool(name: str, arguments: dict) -> str:
            budget.check_wall_clock()
            budget.record_tool_call()
            result = await tool_gateway.execute(
                db, run, context, name, arguments, approved_plan=approved_plan
            )
            if result.denied:
                raise ToolDeniedError(result.error or f"Tool {name!r} was denied.")
            return _observation(result)

        async def record_usage(result: AgentRunResult) -> None:
            # Ledger first, so a breached budget does not drop the record of what was spent.
            await gateway.record_external_usage(
                db,
                organization_id=context.organization_id,
                provider=result.provider,
                model=result.model_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                project_id=context.project_id,
            )
            budget.record_usage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=estimate_cost_usd(
                    result.model_id, result.input_tokens, result.output_tokens
                ),
            )

        async with asyncio.timeout(definition.budget.seconds):
            result = await runner.run(
                definition,
                context,
                prompt=prompt,
                tools=specs,
                tool_executor=execute_tool,
                usage_recorder=record_usage,
            )
    except RunBudgetExceeded as exc:
        await _fail(db, run, FailureClass.TERMINAL, str(exc), budget)
        raise
    except BudgetExceededError as exc:
        await _fail(db, run, FailureClass.TERMINAL, str(exc), budget)
        raise
    except AgentBudgetExceededError as exc:
        await _fail(db, run, FailureClass.TERMINAL, str(exc), budget)
        raise
    except ToolDeniedError as exc:
        await _fail(db, run, FailureClass.REFUSED, str(exc), budget)
        raise
    except TimeoutError as exc:
        await _fail(db, run, FailureClass.TERMINAL, "Run exceeded its wall-clock budget.", budget)
        raise RunBudgetExceeded("seconds") from exc
    except StructuredOutputError as exc:
        await _fail(db, run, FailureClass.NEEDS_HUMAN, str(exc), budget)
        raise
    except AgentRunnerError as exc:
        await _fail(db, run, FailureClass.TERMINAL, str(exc), budget)
        raise
    except Exception as exc:
        # Any other failure still finishes the run rather than leaving it RUNNING.
        await _fail(db, run, FailureClass.TERMINAL, str(exc), budget)
        raise

    try:
        # The caller captures the structured output here; the harness owns the run record.
        if on_result is not None:
            await on_result(result)
        await record_run_metadata(
            db, run, model_version_reported=result.model_version_reported
        )
        run.tokens_used = budget.tokens
        run.cost_usd = budget.cost_usd
        await finish_agent_run(db, run, AgentRunStatus.COMPLETED)
    except Exception as exc:
        # A failure while finalizing must not leave the run RUNNING.
        await _fail(db, run, FailureClass.TERMINAL, str(exc), budget)
        raise
    return run


def _tool_specs(definition: AgentDefinition, registry: ToolRegistry) -> list[ToolSpec]:
    """Only the tools the agent declares, resolved from the registry."""
    return [
        ToolSpec(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in (registry.get(name) for name in definition.tools)
    ]


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _observation(result: ToolResult) -> str:
    if result.is_error:
        return result.error or "The tool failed."
    return json.dumps(result.output, default=str)


async def _fail(
    db: AsyncSession,
    run: AgentRun,
    failure_class: FailureClass,
    reason: str,
    budget: BudgetTracker,
) -> None:
    # The usage consumed before the failure is part of the record, not lost with it (FR-053).
    run.tokens_used = budget.tokens
    run.cost_usd = budget.cost_usd
    await finish_agent_run(
        db,
        run,
        AgentRunStatus.FAILED,
        failure_class=failure_class,
        failure_reason=reason[:2000],
    )
