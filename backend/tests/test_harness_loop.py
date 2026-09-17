"""Step C · C6 — the harness loop and budgets (FR-050, FR-053, FR-054).

One loop: build the run, expose the agent's tools through the gateway, meter the call, enforce the
run budget, and finish the record with a classified failure.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select

from app.agents.base import AgentDefinition, Budget
from app.core.config import settings
from app.core.database import get_session_factory
from app.harness.budget import RunBudgetExceeded
from app.harness.context import ExecutionContext
from app.harness.loop import run_agent
from app.harness.runner import (
    AgentBudgetExceededError,
    AgentRunnerError,
    AgentRunResult,
    StructuredOutputError,
    ToolDeniedError,
)
from app.llm.gateway import ModelGateway
from app.llm.providers.fake import FakeModelProvider
from app.models.agent_run import AgentRun, AgentRunStatus, AgentToolCall, FailureClass
from app.models.model_usage import ModelUsage
from app.tools.base import Tool, ToolKind, ToolResult
from app.tools.gateway import ToolGateway
from app.tools.registry import ToolRegistry

READ_CAP = "repository.read"


class Args(BaseModel):
    path: str = "."


class FakeReadTool(Tool):
    name = "read_tree"
    description = "List files."
    kind = ToolKind.READ
    required_capability = READ_CAP
    input_schema = Args

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        return ToolResult(output={"entries": []})


class FakeRunner:
    """Stands in for the Pydantic AI adapter: it drives the tool executor then returns a result."""

    def __init__(
        self,
        *,
        calls=(),
        error=None,
        error_after_usage=None,
        sleep=0.0,
        input_tokens=100,
        output_tokens=50,
    ) -> None:
        self._calls = calls
        self._error = error
        self._error_after_usage = error_after_usage
        self._sleep = sleep
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self.received_tools: list = []

    async def run(
        self, definition, context, *, prompt, tools=(), tool_executor=None, usage_recorder=None
    ):
        self.received_tools = list(tools)
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._error is not None:
            raise self._error
        for name, arguments in self._calls:
            await tool_executor(name, arguments)
        result = AgentRunResult(
            output=None,
            text="done",
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            provider="fake",
            model_id="gemini-2.5-flash",
            model_version_reported="v1",
        )
        if usage_recorder is not None:
            await usage_recorder(result)
        if self._error_after_usage is not None:
            raise self._error_after_usage
        return result


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


def _definition(
    *, tool_calls: int = 10, tokens: int = 1000, seconds: int = 30, cost: str = "0.10"
) -> AgentDefinition:
    return AgentDefinition(
        name="test_agent",
        version="1.0.0",
        instructions="Do the thing.",
        capabilities=frozenset({READ_CAP}),
        tools=("read_tree",),
        output_schema=None,
        budget=Budget(
            tool_calls=tool_calls, tokens=tokens, seconds=seconds, cost_usd=Decimal(cost)
        ),
    )


def _context(org_id: str, proj_id: str, *, granted: frozenset[str] = frozenset({READ_CAP})):
    return ExecutionContext(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        repository_id=None,
        environment="test",
        agent_name="test_agent",
        agent_version="1.0.0",
        capabilities=granted,
    )


async def _setup(client: AsyncClient, email: str, name: str):
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    return org_id, proj_id


def _deps() -> tuple[ToolGateway, ToolRegistry, ModelGateway]:
    registry = ToolRegistry()
    registry.register(FakeReadTool())
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


# ============================================================
# 1. A successful run
# ============================================================


@pytest.mark.asyncio
async def test_run_completes_and_records_usage_and_tool_calls(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The run record stores the deployment's model id, so this test states the id it expects instead
    # of inheriting `.env`. Inheriting made the assertion a statement about the developer's local
    # configuration rather than about the harness.
    monkeypatch.setattr(settings, "MODEL_ID", "gemini-2.5-flash")
    org_id, proj_id = await _setup(client, "c6_ok@example.com", "C6Ok")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(calls=[("read_tree", {"path": "."})])

    session_factory = get_session_factory()
    async with session_factory() as db:
        run = await _run(
            db, _context(org_id, proj_id), _definition(), runner, tool_gateway, registry, gateway
        )
        await db.commit()
        run_id = run.id

    async with session_factory() as db:
        stored = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        calls = (
            await db.execute(select(AgentToolCall).where(AgentToolCall.agent_run_id == run_id))
        ).scalars().all()
        usage = (await db.execute(select(ModelUsage))).scalars().all()

    assert stored.status == AgentRunStatus.COMPLETED
    assert stored.tokens_used == 150
    assert stored.model_id == "gemini-2.5-flash"
    assert stored.prompt_hash is not None
    assert [c.tool_name for c in calls] == ["read_tree"]
    assert len(usage) == 1


@pytest.mark.asyncio
async def test_only_the_declared_tools_are_exposed(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_tools@example.com", "C6Tools")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner()

    session_factory = get_session_factory()
    async with session_factory() as db:
        await _run(
            db, _context(org_id, proj_id), _definition(), runner, tool_gateway, registry, gateway
        )
        await db.commit()

    assert [spec.name for spec in runner.received_tools] == ["read_tree"]


# ============================================================
# 2. Budgets terminate the run
# ============================================================


@pytest.mark.asyncio
async def test_tool_call_budget_terminates(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_toolbudget@example.com", "C6ToolBudget")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(calls=[("read_tree", {})])

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(RunBudgetExceeded) as excinfo:
            await _run(
                db,
                _context(org_id, proj_id),
                _definition(tool_calls=0),
                runner,
                tool_gateway,
                registry,
                gateway,
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert excinfo.value.limit == "tool_calls"
    assert run.status == AgentRunStatus.FAILED
    assert run.failure_class == FailureClass.TERMINAL


@pytest.mark.asyncio
async def test_token_budget_terminates(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_tokenbudget@example.com", "C6TokenBudget")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(input_tokens=10_000, output_tokens=10_000)

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(RunBudgetExceeded) as excinfo:
            await _run(
                db,
                _context(org_id, proj_id),
                _definition(tokens=100),
                runner,
                tool_gateway,
                registry,
                gateway,
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()
        usage = (await db.execute(select(ModelUsage))).scalars().all()

    assert excinfo.value.limit == "tokens"
    assert run.failure_class == FailureClass.TERMINAL
    # The spend is on the run record and in the ledger, so the overrun is not lost.
    assert run.tokens_used > 0
    assert len(usage) == 1


@pytest.mark.asyncio
async def test_cost_budget_terminates(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_costbudget@example.com", "C6CostBudget")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(input_tokens=1_000_000, output_tokens=1_000_000)

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(RunBudgetExceeded) as excinfo:
            await _run(
                db,
                _context(org_id, proj_id),
                _definition(tokens=10**9, cost="0.001"),
                runner,
                tool_gateway,
                registry,
                gateway,
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert excinfo.value.limit == "cost_usd"
    assert run.failure_class == FailureClass.TERMINAL


@pytest.mark.asyncio
async def test_wall_clock_budget_terminates(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_time@example.com", "C6Time")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(sleep=1.2)

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(RunBudgetExceeded) as excinfo:
            await _run(
                db,
                _context(org_id, proj_id),
                _definition(seconds=1),
                runner,
                tool_gateway,
                registry,
                gateway,
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert excinfo.value.limit == "seconds"
    assert run.failure_class == FailureClass.TERMINAL


# ============================================================
# 3. Failures are classified
# ============================================================


@pytest.mark.asyncio
async def test_a_denied_tool_is_refused(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_denied@example.com", "C6Denied")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(calls=[("read_tree", {})])

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ToolDeniedError):
            await _run(
                db,
                _context(org_id, proj_id, granted=frozenset()),
                _definition(),
                runner,
                tool_gateway,
                registry,
                gateway,
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert run.failure_class == FailureClass.REFUSED


@pytest.mark.asyncio
async def test_structured_output_failure_needs_a_human(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_struct@example.com", "C6Struct")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(error=StructuredOutputError("bad output"))

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(StructuredOutputError):
            await _run(
                db, _context(org_id, proj_id), _definition(), runner, tool_gateway, registry, gateway
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert run.failure_class == FailureClass.NEEDS_HUMAN


@pytest.mark.asyncio
async def test_runner_failure_is_terminal(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_runner@example.com", "C6Runner")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(error=AgentRunnerError("provider down"))

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(AgentRunnerError):
            await _run(
                db, _context(org_id, proj_id), _definition(), runner, tool_gateway, registry, gateway
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert run.failure_class == FailureClass.TERMINAL


@pytest.mark.asyncio
async def test_a_failed_run_keeps_its_usage_on_the_record(client: AsyncClient) -> None:
    org_id, proj_id = await _setup(client, "c6_partial@example.com", "C6Partial")
    tool_gateway, registry, gateway = _deps()
    runner = FakeRunner(error_after_usage=AgentBudgetExceededError("framework limit"))

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(AgentBudgetExceededError):
            await _run(
                db, _context(org_id, proj_id), _definition(), runner, tool_gateway, registry, gateway
            )
        await db.commit()
        run = (await db.execute(select(AgentRun))).scalar_one()

    assert run.status == AgentRunStatus.FAILED
    assert run.tokens_used == 150
    assert run.cost_usd > 0
