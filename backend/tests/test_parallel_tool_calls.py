"""Parallel tool calls must not share the one AsyncSession (step C, FR-069/FR-090).

pydantic-ai runs a model's tool calls concurrently — its ``ToolManager`` default execution mode is
``'parallel'`` — while every call appends to the run's tool-call log on the single request session.
An ``AsyncSession`` is not safe for concurrent use: two interleaved flushes left it in a
pending-rollback state ("the connection is closed"), every analysis of a repository whose model
batched its tool calls died as an unhandled 500, and the failure path then erased the run record
instead of recording it.

These tests pin both halves of the fix: the log write is serialized, and a failed run is recorded
durably even when the caller never commits and even if recording the failure fails the first time.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import PendingRollbackError

import app.harness.loop as loop_module
import app.tools.gateway as gateway_module
from app.agents.base import AgentDefinition, Budget
from app.core.database import get_session_factory
from app.harness.context import ExecutionContext
from app.harness.loop import run_agent
from app.harness.run import start_agent_run
from app.llm.gateway import ModelGateway
from app.llm.providers.fake import FakeModelProvider
from app.models.agent_run import AgentRun, AgentRunStatus, AgentToolCall
from app.tools.base import Tool, ToolKind, ToolResult
from app.tools.gateway import ToolGateway
from app.tools.registry import ToolRegistry

READ_CAP = "repository.read"


class PathArgs(BaseModel):
    path: str


class YieldingReadTool(Tool):
    """A read tool that yields, as a real file read does, to widen the interleaving window."""

    name = "read_tree"
    description = "List files."
    kind = ToolKind.READ
    required_capability = READ_CAP
    input_schema = PathArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        await asyncio.sleep(0)
        return ToolResult(output={"entries": []})


class FailingRunner:
    """A runner that fails the way a provider or tool failure does: with the run already started."""

    async def run(
        self, definition, context, *, prompt, tools=(), tool_executor=None, usage_recorder=None
    ):
        raise RuntimeError("boom")


async def _register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
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


def _definition() -> AgentDefinition:
    return AgentDefinition(
        name="test_agent",
        version="1.0.0",
        instructions="Do the thing.",
        capabilities=frozenset({READ_CAP}),
        tools=("read_tree",),
        output_schema=None,
        budget=Budget(tool_calls=10, tokens=1000, seconds=30, cost_usd=Decimal("0.10")),
    )


def _context(org_id: str, proj_id: str) -> ExecutionContext:
    return ExecutionContext(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        repository_id=None,
        environment="test",
        agent_name="test_agent",
        agent_version="1.0.0",
        capabilities=frozenset({READ_CAP}),
    )


async def _tenant(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    token, org_id = await _register_user(client, email, name)
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"{name} Proj", "slug": f"{name.lower()}-proj"},
    )
    assert resp.status_code == 201
    return org_id, resp.json()["id"]


def _deps() -> tuple[ToolGateway, ToolRegistry, ModelGateway]:
    registry = ToolRegistry()
    registry.register(YieldingReadTool())
    return ToolGateway(registry), registry, ModelGateway(FakeModelProvider())


async def _run(db, context, definition, runner, tool_gateway, registry, gateway):
    return await run_agent(
        db,
        context=context,
        definition=definition,
        prompt="go",
        runner=runner,
        gateway=gateway,
        tool_gateway=tool_gateway,
        registry=registry,
    )


@pytest.mark.asyncio
async def test_parallel_tool_calls_are_serialized_on_the_session(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two tool calls in one model response must not write the log concurrently."""
    org_id, proj_id = await _tenant(client, "cc_parallel@example.com", "CCParallel")
    context = _context(org_id, proj_id)
    tool_gateway, _, _ = _deps()

    session_factory = get_session_factory()
    async with session_factory() as db:
        run = await start_agent_run(db, context, _definition())

    in_flight = 0
    overlapped = False
    original = gateway_module.record_tool_call

    async def probing_record_tool_call(*args, **kwargs):
        nonlocal in_flight, overlapped
        in_flight += 1
        if in_flight > 1:
            overlapped = True
        await asyncio.sleep(0)
        try:
            return await original(*args, **kwargs)
        finally:
            in_flight -= 1

    monkeypatch.setattr(gateway_module, "record_tool_call", probing_record_tool_call)

    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run.id))).scalar_one()
        await asyncio.gather(
            tool_gateway.execute(db, run, context, "read_tree", {"path": "a.tsx"}),
            tool_gateway.execute(db, run, context, "read_tree", {"path": "b.tsx"}),
        )
        await db.commit()
        run_id = run.id

    assert overlapped is False, "the tool-call log write ran concurrently on one AsyncSession"

    async with session_factory() as db:
        calls = (
            await db.execute(
                select(AgentToolCall)
                .where(AgentToolCall.agent_run_id == run_id)
                .order_by(AgentToolCall.sequence)
            )
        ).scalars().all()

    assert [call.tool_name for call in calls] == ["read_tree", "read_tree"]
    assert sorted(call.sequence for call in calls) == [1, 2], "sequences must be unique and ordered"


@pytest.mark.asyncio
async def test_a_failed_run_is_recorded_even_if_the_caller_never_commits(
    client: AsyncClient,
) -> None:
    """A run that fails must leave a FAILED record, not vanish with the caller's transaction."""
    org_id, proj_id = await _tenant(client, "cc_durable@example.com", "CCDurable")
    tool_gateway, registry, gateway = _deps()

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(RuntimeError, match="boom"):
            await _run(
                db,
                _context(org_id, proj_id),
                _definition(),
                FailingRunner(),
                tool_gateway,
                registry,
                gateway,
            )
        # Deliberately no commit: the harness owns its record.

    async with session_factory() as db:
        stored = (
            await db.execute(
                select(AgentRun).where(AgentRun.project_id == uuid.UUID(proj_id))
            )
        ).scalar_one()

    assert stored.status == AgentRunStatus.FAILED
    assert stored.failure_reason == "boom"


@pytest.mark.asyncio
async def test_a_poisoned_session_does_not_mask_the_original_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If recording the failure itself fails, recover on a clean transaction and keep the cause."""
    org_id, proj_id = await _tenant(client, "cc_recover@example.com", "CCRecover")
    tool_gateway, registry, gateway = _deps()

    attempts = 0
    original = loop_module.finish_agent_run

    async def flaky_finish_agent_run(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PendingRollbackError("simulated: the session is in a pending-rollback state")
        return await original(*args, **kwargs)

    monkeypatch.setattr(loop_module, "finish_agent_run", flaky_finish_agent_run)

    session_factory = get_session_factory()
    async with session_factory() as db:
        # The original error must surface, not the PendingRollbackError from the failed recording.
        with pytest.raises(RuntimeError, match="boom"):
            await _run(
                db,
                _context(org_id, proj_id),
                _definition(),
                FailingRunner(),
                tool_gateway,
                registry,
                gateway,
            )

    assert attempts == 2, "the failure recording should have been retried once"

    async with session_factory() as db:
        stored = (
            await db.execute(
                select(AgentRun).where(AgentRun.project_id == uuid.UUID(proj_id))
            )
        ).scalar_one()

    assert stored.status == AgentRunStatus.FAILED
    assert stored.failure_reason == "boom"
