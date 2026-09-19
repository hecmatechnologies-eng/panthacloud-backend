"""AgentRun persistence (FR-051, FR-089).

Infrastructure the harness owns: create a run from a trusted context, finish it, and record its
reproducibility metadata. Kept out of the loop so the loop stays about control flow. This is the
documented exception to CLAUDE.md §5's "the harness reaches the database only through tools" — an
``AgentRun`` is the harness's own record, not a capability granted to the model. Tool calls are
recorded by the tool gateway (`app/tools/gateway.py`), which owns that half of the run record.
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentDefinition
from app.harness.context import ExecutionContext
from app.models.agent_run import AgentRun, AgentRunStatus, FailureClass
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
    # Commit before the model is called. A run that fails must still leave a record (FR-089), and a
    # session poisoned mid-run must not be able to erase one that was only flushed.
    await db.commit()

    if context.project_id is not None:
        try:
            import json
            from app.core.redis import get_redis, project_event_channel

            client = get_redis()
            if client is not None:
                channel = project_event_channel(context.project_id)
                payload = {
                    "id": str(run.id),
                    "event_type": f"agent.run.{definition.name}.started",
                    "payload": {
                        "run_id": str(run.id),
                        "agent_name": definition.name,
                        "agent_version": definition.version,
                    },
                    "created_at": run.started_at.isoformat(),
                }
                await client.publish(channel, json.dumps(payload))
        except Exception:
            pass

    return run


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
    # Committed, not flushed: the terminal state is the half of the record that must survive even
    # when the caller's transaction is later rolled back.
    await db.commit()

    if run.project_id is not None:
        try:
            import json
            from app.core.redis import get_redis, project_event_channel

            client = get_redis()
            if client is not None:
                channel = project_event_channel(run.project_id)
                event_name = (
                    f"agent.run.{run.agent_name}.completed"
                    if status == AgentRunStatus.COMPLETED
                    else f"agent.run.{run.agent_name}.failed"
                )
                payload = {
                    "id": str(run.id),
                    "event_type": event_name,
                    "payload": {
                        "run_id": str(run.id),
                        "agent_name": run.agent_name,
                        "status": status.value if hasattr(status, "value") else str(status),
                        "failure_reason": failure_reason,
                    },
                    "created_at": run.completed_at.isoformat() if run.completed_at else utc_now().isoformat(),
                }
                await client.publish(channel, json.dumps(payload))
        except Exception:
            pass


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
