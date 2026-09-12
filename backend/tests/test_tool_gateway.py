"""Step C · C3 — the tool gateway (FR-064–070).

Authorization, execution and recording through one choke point: read auto-authorized, write behind
an approved plan, denials and errors model-readable, arguments redacted, scope from the context.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select

from app.agents.base import AgentDefinition, Budget
from app.core.database import get_session_factory
from app.harness.context import ExecutionContext
from app.harness.run import start_agent_run
from app.models.agent_run import AgentRun, AgentToolCall
from app.tools.base import Tool, ToolError, ToolKind, ToolResult
from app.tools.gateway import ApprovedPlan, ToolGateway, redact_arguments
from app.tools.registry import ToolNotFoundError, ToolRegistry

READ_CAP = "repository.read"
WRITE_CAP = "workspace.write"


class PathArgs(BaseModel):
    path: str


class OptionalArgs(BaseModel):
    path: str = "."
    token: str | None = None


class ScopedArgs(BaseModel):
    organization_id: str | None = None


class FakeTool(Tool):
    def __init__(
        self,
        name: str,
        kind: ToolKind,
        capability: str,
        schema: type[BaseModel],
        *,
        result: ToolResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.description = "A fake tool."
        self.kind = kind
        self.required_capability = capability
        self.input_schema = schema
        self._result = result or ToolResult(output="ok")
        self._error = error

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        if self._error is not None:
            raise self._error
        return self._result


class ScopeReportingTool(Tool):
    name = "scope_report"
    description = "Reports the tenancy it resolved from its context."
    kind = ToolKind.READ
    required_capability = READ_CAP
    input_schema = ScopedArgs

    async def execute(self, context: ExecutionContext, arguments: BaseModel) -> ToolResult:
        return ToolResult(output={"organization_id": str(context.organization_id)})


# ============================================================
# Fixtures / helpers
# ============================================================


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


async def make_run(
    client: AsyncClient,
    email: str,
    name: str,
    declared: frozenset[str],
    granted: frozenset[str],
) -> tuple[ExecutionContext, uuid.UUID]:
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    definition = AgentDefinition(
        name="test_agent",
        version="1.0.0",
        instructions="...",
        capabilities=declared,
        tools=(),
        output_schema=None,
        budget=Budget(tool_calls=10, tokens=1000, seconds=30, cost_usd=Decimal("0.10")),
    )
    context = ExecutionContext(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        repository_id=None,
        environment="test",
        agent_name="test_agent",
        agent_version="1.0.0",
        capabilities=granted,
    )
    session_factory = get_session_factory()
    async with session_factory() as db:
        run = await start_agent_run(db, context, definition)
        await db.commit()
        return context, run.id


async def call(
    gateway: ToolGateway,
    run_id: uuid.UUID,
    context: ExecutionContext,
    tool_name: str,
    arguments: dict | None = None,
    **kwargs,
) -> ToolResult:
    session_factory = get_session_factory()
    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        result = await gateway.execute(db, run, context, tool_name, arguments or {}, **kwargs)
        await db.commit()
        return result


async def recorded_calls(run_id: uuid.UUID) -> list[AgentToolCall]:
    session_factory = get_session_factory()
    async with session_factory() as db:
        return list(
            (
                await db.execute(
                    select(AgentToolCall)
                    .where(AgentToolCall.agent_run_id == run_id)
                    .order_by(AgentToolCall.sequence)
                )
            )
            .scalars()
            .all()
        )


def gateway_with(*tools: Tool) -> ToolGateway:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return ToolGateway(registry)


# ============================================================
# 1. Read/write authorization
# ============================================================


@pytest.mark.asyncio
async def test_read_tool_is_auto_authorized(client: AsyncClient) -> None:
    read = FakeTool("read_file", ToolKind.READ, READ_CAP, PathArgs)
    gateway = gateway_with(read)
    context, run_id = await make_run(
        client, "c3_read@example.com", "C3Read", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(gateway, run_id, context, "read_file", {"path": "app/layout.tsx"})
    assert result.is_error is False
    assert result.output == "ok"
    assert [c.outcome for c in await recorded_calls(run_id)] == ["ok"]


@pytest.mark.asyncio
async def test_read_tool_is_denied_without_the_capability(client: AsyncClient) -> None:
    read = FakeTool("read_file", ToolKind.READ, READ_CAP, PathArgs)
    gateway = gateway_with(read)
    # The definition declares the capability, but the granted context does not (narrowing).
    context, run_id = await make_run(
        client, "c3_nocap@example.com", "C3NoCap", frozenset({READ_CAP}), frozenset()
    )

    result = await call(gateway, run_id, context, "read_file", {"path": "x"})
    assert result.denied is True
    assert "lacks" in (result.error or "")
    calls = await recorded_calls(run_id)
    assert calls[0].outcome == "denied"


@pytest.mark.asyncio
async def test_write_tool_requires_an_approved_plan(client: AsyncClient) -> None:
    write = FakeTool("write_file", ToolKind.WRITE, WRITE_CAP, PathArgs)
    gateway = gateway_with(write)
    context, run_id = await make_run(
        client, "c3_write@example.com", "C3Write", frozenset({WRITE_CAP}), frozenset({WRITE_CAP})
    )

    denied = await call(gateway, run_id, context, "write_file", {"path": "x"})
    assert denied.denied is True
    assert "approved plan" in (denied.error or "")

    approved = await call(
        gateway,
        run_id,
        context,
        "write_file",
        {"path": "x"},
        approved_plan=ApprovedPlan(plan_id="plan-1", approved_by=uuid.uuid4()),
    )
    assert approved.is_error is False
    assert [c.outcome for c in await recorded_calls(run_id)] == ["denied", "ok"]


# ============================================================
# 2. Errors are model-readable
# ============================================================


@pytest.mark.asyncio
async def test_unknown_tool_is_a_readable_error(client: AsyncClient) -> None:
    gateway = gateway_with()
    context, run_id = await make_run(
        client, "c3_unknown@example.com", "C3Unknown", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(gateway, run_id, context, "does_not_exist", {})
    assert result.denied is False
    assert result.is_error is True
    assert "does_not_exist" in (result.error or "")
    assert (await recorded_calls(run_id))[0].outcome == "unknown"


@pytest.mark.asyncio
async def test_invalid_arguments_are_reported_without_echoing_values(client: AsyncClient) -> None:
    read = FakeTool("read_file", ToolKind.READ, READ_CAP, PathArgs)
    gateway = gateway_with(read)
    context, run_id = await make_run(
        client, "c3_invalid@example.com", "C3Invalid", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(gateway, run_id, context, "read_file", {"wrong": "value"})
    assert result.is_error is True
    assert "path" in (result.error or "")
    assert "value" not in (result.error or "")
    assert (await recorded_calls(run_id))[0].outcome == "error"


@pytest.mark.asyncio
async def test_tool_error_is_returned_to_the_model(client: AsyncClient) -> None:
    failing = FakeTool(
        "read_file",
        ToolKind.READ,
        READ_CAP,
        PathArgs,
        error=ToolError("File not found: components/App.tsx. Did you mean src/components/App.tsx?"),
    )
    gateway = gateway_with(failing)
    context, run_id = await make_run(
        client, "c3_toolerr@example.com", "C3ToolErr", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(gateway, run_id, context, "read_file", {"path": "components/App.tsx"})
    assert "Did you mean" in (result.error or "")
    assert (await recorded_calls(run_id))[0].outcome == "error"


@pytest.mark.asyncio
async def test_unexpected_exception_is_not_leaked(client: AsyncClient) -> None:
    crashing = FakeTool(
        "read_file", ToolKind.READ, READ_CAP, PathArgs, error=RuntimeError("internal secret detail")
    )
    gateway = gateway_with(crashing)
    context, run_id = await make_run(
        client, "c3_crash@example.com", "C3Crash", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(gateway, run_id, context, "read_file", {"path": "x"})
    assert result.error == "The tool failed unexpectedly."
    assert "internal secret detail" not in (result.error or "")


# ============================================================
# 3. Recording, redaction, truncation, scope
# ============================================================


@pytest.mark.asyncio
async def test_successful_call_is_recorded_with_redacted_arguments(client: AsyncClient) -> None:
    read = FakeTool("read_file", ToolKind.READ, READ_CAP, OptionalArgs)
    gateway = gateway_with(read)
    context, run_id = await make_run(
        client, "c3_redact@example.com", "C3Redact", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    await call(gateway, run_id, context, "read_file", {"path": "x", "token": "super-secret-value"})
    call_row = (await recorded_calls(run_id))[0]
    assert call_row.arguments["path"] == "x"
    assert call_row.arguments["token"] == "[REDACTED]"
    assert call_row.duration_ms >= 0


def test_redact_arguments_recurses() -> None:
    redacted = redact_arguments(
        {
            "api_key": "abc",
            "path": "app/layout.tsx",
            "nested": {"password": "x", "ok": "y"},
            "list": [{"secret": "z"}],
        }
    )
    assert redacted == {
        "api_key": "[REDACTED]",
        "path": "app/layout.tsx",
        "nested": {"password": "[REDACTED]", "ok": "y"},
        "list": [{"secret": "[REDACTED]"}],
    }


@pytest.mark.parametrize(
    "key",
    ["github_token", "apiKey", "X-Api-Key", "session_id", "auth", "personal_pat", "credentials"],
)
def test_sensitive_key_names_are_redacted(key: str) -> None:
    assert redact_arguments({"value": "secret"}, key) == "[REDACTED]"


@pytest.mark.parametrize("key", ["path", "filename", "keyword", "monkey", "source_file"])
def test_ordinary_key_names_are_preserved(key: str) -> None:
    assert redact_arguments({"value": "keep"}, key) == {"value": "keep"}


@pytest.mark.asyncio
async def test_gateway_rejects_a_run_from_another_tenant(client: AsyncClient) -> None:
    gateway = gateway_with(FakeTool("read_file", ToolKind.READ, READ_CAP, PathArgs))
    _, run_a = await make_run(
        client, "c3_tenant_a@example.com", "C3TenantA", frozenset({READ_CAP}), frozenset({READ_CAP})
    )
    context_b, _ = await make_run(
        client, "c3_tenant_b@example.com", "C3TenantB", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_a))).scalar_one()
        with pytest.raises(ValueError):
            await gateway.execute(db, run, context_b, "read_file", {"path": "x"})


@pytest.mark.asyncio
async def test_truncation_is_signalled(client: AsyncClient) -> None:
    truncated = FakeTool(
        "read_file",
        ToolKind.READ,
        READ_CAP,
        PathArgs,
        result=ToolResult(output="partial", truncated=True),
    )
    gateway = gateway_with(truncated)
    context, run_id = await make_run(
        client, "c3_trunc@example.com", "C3Trunc", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(gateway, run_id, context, "read_file", {"path": "big.txt"})
    assert result.truncated is True


@pytest.mark.asyncio
async def test_scope_comes_from_context_not_arguments(client: AsyncClient) -> None:
    gateway = gateway_with(ScopeReportingTool())
    context, run_id = await make_run(
        client, "c3_scope@example.com", "C3Scope", frozenset({READ_CAP}), frozenset({READ_CAP})
    )

    result = await call(
        gateway, run_id, context, "scope_report", {"organization_id": "attacker-supplied"}
    )
    assert result.output == {"organization_id": str(context.organization_id)}


# ============================================================
# 4. Registry
# ============================================================


def test_registry_rejects_duplicate_and_reports_missing() -> None:
    registry = ToolRegistry()
    registry.register(FakeTool("read_file", ToolKind.READ, READ_CAP, PathArgs))
    with pytest.raises(ValueError):
        registry.register(FakeTool("read_file", ToolKind.READ, READ_CAP, PathArgs))
    with pytest.raises(ToolNotFoundError):
        registry.get("nope")
