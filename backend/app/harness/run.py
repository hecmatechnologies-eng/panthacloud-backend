"""AgentRun persistence (FR-051, FR-090).

Infrastructure the harness owns: create a run from a trusted context, append ordered tool calls, and
finish it. Kept out of the loop so the loop stays about control flow. This is the documented
exception to CLAUDE.md §5's "the harness reaches the database only through tools" — an ``AgentRun``
is the harness's own record, not a capability granted to the model.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentDefinition
from app.harness.context import ExecutionContext
from app.models.agent_run import AgentRun, AgentRunStatus, AgentToolCall, FailureClass
from app.models.base import utc_now


async def start_agent_run(
    db: AsyncSession, context: ExecutionContext, definition: AgentDefinition
) -> AgentRun:
    _assert_context_matches(context, definition)
    run = AgentRun(
        organization_id=context.organization_id,
        project_id=context.project_id,
        repository_id=context.repository_id,
        agent_name=definition.name,
        agent_version=definition.version,
        status=AgentRunStatus.RUNNING,
        attempt=1,
        budget={
            "tool_calls": definition.budget.tool_calls,
            "tokens": definition.budget.tokens,
            "seconds": definition.budget.seconds,
            "cost_usd": str(definition.budget.cost_usd),
        },
        execution_context=context.snapshot(),
        skill_versions={},
        tokens_used=0,
        cost_usd=Decimal(0),
        started_at=utc_now(),
    )
    db.add(run)
    await db.flush()
    return run


async def record_tool_call(
    db: AsyncSession,
    run: AgentRun,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    outcome: str,
    duration_ms: int,
    error_message: str | None = None,
) -> AgentToolCall:
    call = AgentToolCall(
        agent_run_id=run.id,
        sequence=await _next_sequence(db, run.id),
        tool_name=tool_name,
        arguments=arguments,
        outcome=outcome,
        duration_ms=duration_ms,
        error_message=error_message,
    )
    db.add(call)
    await db.flush()
    return call


async def finish_agent_run(
    db: AsyncSession,
    run: AgentRun,
    status: AgentRunStatus,
    *,
    failure_class: FailureClass | None = None,
    failure_reason: str | None = None,
) -> None:
    run.status = status
    run.failure_class = failure_class
    run.failure_reason = failure_reason
    run.completed_at = utc_now()
    await db.flush()


async def record_run_metadata(
    db: AsyncSession,
    run: AgentRun,
    *,
    prompt_hash: str | None = None,
    model_id: str | None = None,
    model_version_reported: str | None = None,
    skill_versions: dict[str, str] | None = None,
) -> None:
    """Write the reproducibility fields FR-089 requires, as each becomes known."""
    if prompt_hash is not None:
        run.prompt_hash = prompt_hash
    if model_id is not None:
        run.model_id = model_id
    if model_version_reported is not None:
        run.model_version_reported = model_version_reported
    if skill_versions is not None:
        run.skill_versions = skill_versions
    await db.flush()


def _assert_context_matches(context: ExecutionContext, definition: AgentDefinition) -> None:
    """A run must not be started for a context that describes a different agent.

    The context may grant a *subset* of the agent's declared capabilities — capability narrowing by
    workflow state (FR-094) — but never one the agent does not declare.
    """
    if context.agent_name != definition.name or context.agent_version != definition.version:
        raise ValueError(
            f"ExecutionContext is for {context.agent_name!r} {context.agent_version!r}, but the "
            f"definition is {definition.name!r} {definition.version!r}."
        )
    undeclared = context.capabilities - definition.capabilities
    if undeclared:
        raise ValueError(
            f"ExecutionContext grants capabilities the agent does not declare: {sorted(undeclared)}."
        )


async def _next_sequence(db: AsyncSession, agent_run_id: uuid.UUID) -> int:
    stmt = select(func.max(AgentToolCall.sequence)).where(
        AgentToolCall.agent_run_id == agent_run_id
    )
    current = (await db.execute(stmt)).scalar_one_or_none()
    return (current or 0) + 1
