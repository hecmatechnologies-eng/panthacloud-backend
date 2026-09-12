"""Step C · C2 — the agent runtime substrate (FR-046–049, FR-051, FR-090).

ExecutionContext, agent definitions and registry, and AgentRun persistence with its ordered tool-call
log. No model call and no harness loop yet — those are C5/C6.
"""

import dataclasses
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.agents.base import AgentDefinition, Budget
from app.agents.registry import AgentNotFoundError, AgentRegistry
from app.core.database import get_session_factory
from app.harness.context import ExecutionContext
from app.harness.run import (
    finish_agent_run,
    record_run_metadata,
    record_tool_call,
    start_agent_run,
)
from app.models.agent_run import AgentRun, AgentRunStatus, AgentToolCall, FailureClass

CAPABILITIES = frozenset({"repository.read"})


def _definition(name: str = "test_agent", version: str = "1.0.0") -> AgentDefinition:
    return AgentDefinition(
        name=name,
        version=version,
        instructions="Read the repository and report what you find.",
        capabilities=CAPABILITIES,
        tools=("read_tree", "read_file"),
        output_schema=None,
        budget=Budget(tool_calls=10, tokens=1000, seconds=30, cost_usd=Decimal("0.10")),
    )


def _context(org_id: uuid.UUID, proj_id: uuid.UUID) -> ExecutionContext:
    return ExecutionContext(
        organization_id=org_id,
        project_id=proj_id,
        repository_id=None,
        environment="test",
        agent_name="test_agent",
        agent_version="1.0.0",
        capabilities=CAPABILITIES,
    )


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": f"{name}'s Org",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return token, orgs.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def tenant(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    return token, org_id, proj_id


# ============================================================
# 1. ExecutionContext
# ============================================================


def test_context_is_frozen_and_carries_capabilities() -> None:
    ctx = _context(uuid.uuid4(), uuid.uuid4())
    assert ctx.has_capability("repository.read")
    assert not ctx.has_capability("workspace.write")

    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.organization_id = uuid.uuid4()  # type: ignore[misc]


def test_bind_run_returns_a_new_context() -> None:
    ctx = _context(uuid.uuid4(), uuid.uuid4())
    run_id = uuid.uuid4()
    bound = ctx.bind_run(run_id)

    assert bound.agent_run_id == run_id
    assert ctx.agent_run_id is None  # the original is untouched
    assert bound.snapshot()["agent_run_id"] == str(run_id)


def test_context_snapshot_is_serializable_and_labels_tenancy() -> None:
    org_id, proj_id = uuid.uuid4(), uuid.uuid4()
    snapshot = _context(org_id, proj_id).snapshot()
    assert snapshot["organization_id"] == str(org_id)
    assert snapshot["project_id"] == str(proj_id)
    assert snapshot["repository_id"] is None
    assert snapshot["capabilities"] == ["repository.read"]


# ============================================================
# 2. Agent definition + registry
# ============================================================


def test_registry_registers_and_resolves() -> None:
    registry = AgentRegistry()
    definition = _definition()
    registry.register(definition)

    assert registry.get("test_agent", "1.0.0") is definition
    assert registry.list() == [definition]

    with pytest.raises(AgentNotFoundError):
        registry.get("test_agent", "9.9.9")
    with pytest.raises(AgentNotFoundError):
        registry.get("unknown", "1.0.0")


def test_registry_rejects_duplicate_registration() -> None:
    registry = AgentRegistry()
    registry.register(_definition())
    with pytest.raises(ValueError):
        registry.register(_definition())


# ============================================================
# 3. AgentRun persistence
# ============================================================


@pytest.mark.asyncio
async def test_start_agent_run_persists_context_and_budget(client: AsyncClient) -> None:
    _, org_id, proj_id = await tenant(client, "c2_start@example.com", "C2Start")
    definition = _definition()
    ctx = _context(uuid.UUID(org_id), uuid.UUID(proj_id))

    session_factory = get_session_factory()
    async with session_factory() as db:
        run = await start_agent_run(db, ctx, definition)
        await db.commit()
        run_id = run.id

    async with session_factory() as db:
        stored = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()

    assert stored.agent_name == "test_agent"
    assert stored.agent_version == "1.0.0"
    assert stored.status == AgentRunStatus.RUNNING
    assert stored.organization_id == uuid.UUID(org_id)
    assert stored.execution_context["project_id"] == proj_id
    assert stored.budget["tool_calls"] == 10
    assert stored.started_at is not None


@pytest.mark.asyncio
async def test_tool_calls_are_recorded_in_order(client: AsyncClient) -> None:
    _, org_id, proj_id = await tenant(client, "c2_calls@example.com", "C2Calls")
    session_factory = get_session_factory()

    async with session_factory() as db:
        run = await start_agent_run(
            db, _context(uuid.UUID(org_id), uuid.UUID(proj_id)), _definition()
        )
        for name in ("read_tree", "read_file", "search_code"):
            await record_tool_call(
                db,
                run,
                tool_name=name,
                arguments={"path": "app/layout.tsx"},
                outcome="ok",
                duration_ms=12,
            )
        await db.commit()
        run_id = run.id

    async with session_factory() as db:
        calls = (
            await db.execute(
                select(AgentToolCall)
                .where(AgentToolCall.agent_run_id == run_id)
                .order_by(AgentToolCall.sequence)
            )
        ).scalars().all()

    assert [c.tool_name for c in calls] == ["read_tree", "read_file", "search_code"]
    assert [c.sequence for c in calls] == [1, 2, 3]


@pytest.mark.asyncio
async def test_finish_agent_run_records_failure_class(client: AsyncClient) -> None:
    _, org_id, proj_id = await tenant(client, "c2_finish@example.com", "C2Finish")
    session_factory = get_session_factory()

    async with session_factory() as db:
        run = await start_agent_run(
            db, _context(uuid.UUID(org_id), uuid.UUID(proj_id)), _definition()
        )
        await finish_agent_run(
            db,
            run,
            AgentRunStatus.FAILED,
            failure_class=FailureClass.REFUSED,
            failure_reason="No safe integration point.",
        )
        await db.commit()
        run_id = run.id

    async with session_factory() as db:
        stored = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()

    assert stored.status == AgentRunStatus.FAILED
    assert stored.failure_class == FailureClass.REFUSED
    assert stored.failure_reason == "No safe integration point."
    assert stored.completed_at is not None


@pytest.mark.asyncio
async def test_start_rejects_a_context_for_a_different_agent(client: AsyncClient) -> None:
    _, org_id, proj_id = await tenant(client, "c2_mismatch@example.com", "C2Mismatch")
    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ValueError):
            await start_agent_run(
                db,
                _context(uuid.UUID(org_id), uuid.UUID(proj_id)),
                _definition(name="other_agent"),
            )


@pytest.mark.asyncio
async def test_start_allows_capability_narrowing_but_not_widening(client: AsyncClient) -> None:
    _, org_id, proj_id = await tenant(client, "c2_caps@example.com", "C2Caps")
    session_factory = get_session_factory()
    definition = _definition()

    narrowed = dataclasses.replace(
        _context(uuid.UUID(org_id), uuid.UUID(proj_id)), capabilities=frozenset()
    )
    async with session_factory() as db:
        await start_agent_run(db, narrowed, definition)  # a subset is allowed
        await db.commit()

    widened = dataclasses.replace(
        _context(uuid.UUID(org_id), uuid.UUID(proj_id)),
        capabilities=frozenset({"repository.read", "workspace.write"}),
    )
    async with session_factory() as db:
        with pytest.raises(ValueError):
            await start_agent_run(db, widened, definition)


@pytest.mark.asyncio
async def test_record_run_metadata_persists_reproducibility(client: AsyncClient) -> None:
    _, org_id, proj_id = await tenant(client, "c2_meta@example.com", "C2Meta")
    session_factory = get_session_factory()
    async with session_factory() as db:
        run = await start_agent_run(
            db, _context(uuid.UUID(org_id), uuid.UUID(proj_id)), _definition()
        )
        await record_run_metadata(
            db,
            run,
            prompt_hash="a" * 64,
            model_id="kimi-k2.6",
            model_version_reported="2026-09-01",
            skill_versions={"nextjs-app-router": "1.0.0"},
        )
        await db.commit()
        run_id = run.id

    async with session_factory() as db:
        stored = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()

    assert stored.prompt_hash == "a" * 64
    assert stored.model_id == "kimi-k2.6"
    assert stored.model_version_reported == "2026-09-01"
    assert stored.skill_versions == {"nextjs-app-router": "1.0.0"}


@pytest.mark.asyncio
async def test_deleting_project_purges_runs_and_tool_calls(client: AsyncClient) -> None:
    token, org_id, proj_id = await tenant(client, "c2_cascade@example.com", "C2Cascade")
    session_factory = get_session_factory()

    async with session_factory() as db:
        run = await start_agent_run(
            db, _context(uuid.UUID(org_id), uuid.UUID(proj_id)), _definition()
        )
        await record_tool_call(
            db,
            run,
            tool_name="read_tree",
            arguments={},
            outcome="ok",
            duration_ms=1,
        )
        await db.commit()

    async def counts() -> tuple[int, int]:
        async with session_factory() as db:
            runs = (await db.execute(select(func.count()).select_from(AgentRun))).scalar_one()
            calls = (await db.execute(select(func.count()).select_from(AgentToolCall))).scalar_one()
        return runs, calls

    assert await counts() == (1, 1)

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    assert await counts() == (0, 0)
