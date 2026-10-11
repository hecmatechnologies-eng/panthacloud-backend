"""Record approval provenance on write tool calls (OWASP ASI09, standards-alignment.md G7).

`ApprovedPlan` was a runtime gate only — it stopped an unauthorised write, but nothing
persisted who authorised it, so a write tool call in the run log was indistinguishable from
one the agent performed on its own authority. These tests pin both halves: the value is
honest about *who*, and the record survives.
"""

import uuid
from decimal import Decimal

import pytest

from app.tools.gateway import ApprovedPlan, ApproverKind


class TestApproverKind:
    def test_human_is_the_default(self) -> None:
        assert (
            ApprovedPlan(plan_id="p", approved_by=uuid.uuid4()).approver_kind
            is ApproverKind.HUMAN
        )

    def test_a_human_approval_must_name_someone(self) -> None:
        with pytest.raises(ValueError):
            ApprovedPlan(plan_id="p", approved_by=None, approver_kind=ApproverKind.HUMAN)

    def test_a_policy_approval_may_be_attributed_to_the_organization(self) -> None:
        plan = ApprovedPlan(
            plan_id="p", approved_by=uuid.uuid4(), approver_kind=ApproverKind.POLICY
        )
        assert plan.approver_kind is ApproverKind.POLICY

    def test_the_two_kinds_are_distinguishable_by_value(self) -> None:
        """The record is a string column, so the distinction must survive the round trip."""
        assert ApproverKind.HUMAN.value == "human"
        assert ApproverKind.POLICY.value == "policy"
        assert ApproverKind.HUMAN.value != ApproverKind.POLICY.value


async def _seed_run(db, *, agent_name: str, capability: str):
    """An org, project and AgentRun, so the tool-call FKs resolve."""
    from app.agents.base import AgentDefinition, Budget
    from app.harness.context import ExecutionContext
    from app.harness.run import start_agent_run
    from app.models.organization import Organization
    from app.models.project import Project

    org = Organization(id=uuid.uuid4(), name="Approver Org", slug=f"appr-{uuid.uuid4().hex[:8]}")
    db.add(org)
    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Approver Project",
        slug=f"appr-{uuid.uuid4().hex[:8]}",
    )
    db.add(project)
    await db.flush()

    definition = AgentDefinition(
        name=agent_name,
        version="1.0.0",
        instructions="...",
        capabilities=frozenset({capability}),
        tools=(),
        output_schema=None,
        budget=Budget(tool_calls=10, tokens=1000, seconds=30, cost_usd=Decimal("0.10")),
    )
    context = ExecutionContext(
        organization_id=org.id,
        project_id=project.id,
        repository_id=None,
        environment="test",
        agent_name=agent_name,
        agent_version="1.0.0",
        capabilities=frozenset({capability}),
    )
    return await start_agent_run(db, context, definition)


@pytest.mark.asyncio
async def test_a_write_call_records_who_approved_it(db_session) -> None:
    """ASI09 asks for an immutable record of what was authorised, not only what ran."""
    from sqlalchemy import select

    from app.models.agent_run import AgentToolCall
    from app.tools.gateway import record_tool_call

    run = await _seed_run(db_session, agent_name="coding_agent", capability="workspace.write")

    approver = uuid.uuid4()
    await record_tool_call(
        db_session,
        run,
        tool_name="write_file",
        arguments={"path": "app/layout.tsx"},
        outcome="ok",
        duration_ms=5,
        approved_plan=ApprovedPlan(plan_id="plan-123", approved_by=approver),
    )
    await db_session.commit()

    call = (await db_session.execute(select(AgentToolCall))).scalar_one()
    assert call.approved_by == approver
    assert call.approver_kind == "human"
    assert call.approved_plan_id == "plan-123"


@pytest.mark.asyncio
async def test_a_denied_write_still_records_what_authorised_the_attempt(db_session) -> None:
    """A refused write was still authorised by something, and that belongs in the trail."""
    from sqlalchemy import select

    from app.models.agent_run import AgentToolCall
    from app.tools.gateway import record_tool_call

    run = await _seed_run(db_session, agent_name="coding_agent", capability="workspace.write")

    approver = uuid.uuid4()
    await record_tool_call(
        db_session,
        run,
        tool_name="write_file",
        arguments={"path": "app/layout.tsx"},
        outcome="denied",
        duration_ms=1,
        error_message="Not permitted: a write tool requires an approved plan.",
        approved_plan=ApprovedPlan(plan_id="plan-456", approved_by=approver),
    )
    await db_session.commit()

    call = (await db_session.execute(select(AgentToolCall))).scalar_one()
    assert call.outcome == "denied"
    assert call.approved_plan_id == "plan-456"


@pytest.mark.asyncio
async def test_a_read_call_records_no_approval(db_session) -> None:
    """Reads are auto-authorised by capability, so a null approval is the correct record —
    writing one would imply a review that never happened."""
    from sqlalchemy import select

    from app.models.agent_run import AgentToolCall
    from app.tools.gateway import record_tool_call

    run = await _seed_run(db_session, agent_name="website_analyst", capability="repository.read")

    await record_tool_call(
        db_session,
        run,
        tool_name="read_file",
        arguments={"path": "app/layout.tsx"},
        outcome="ok",
        duration_ms=3,
    )
    await db_session.commit()

    call = (await db_session.execute(select(AgentToolCall))).scalar_one()
    assert call.approved_by is None
    assert call.approver_kind is None
    assert call.approved_plan_id is None


def test_the_pipeline_marks_a_userless_background_run_as_policy_approval() -> None:
    """The ARQ task path genuinely runs without a user, so it must be visibly distinct from
    a person clicking approve."""
    import inspect

    from app.services.integration.pipeline import IntegrationPipeline

    source = inspect.getsource(IntegrationPipeline.execute)
    assert "ApproverKind.HUMAN if user_id else ApproverKind.POLICY" in source
    assert "approved_by=user_id or org_id" in source


def test_the_migration_exists_and_is_wired_to_head() -> None:
    """A column the model declares but no migration creates is a crash at deploy time."""
    from pathlib import Path

    from app.models.agent_run import AgentToolCall

    columns = {c.name for c in AgentToolCall.__table__.columns}
    assert {"approved_by", "approver_kind", "approved_plan_id"} <= columns

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions.glob("*0031_tool_call_approval*"))
    assert len(matches) == 1, "migration file missing or duplicated"
    body = matches[0].read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0030_knowledge_storage"' in body
    for column in ("approved_by", "approver_kind", "approved_plan_id"):
        assert column in body, f"{column} declared on the model but not in the migration"