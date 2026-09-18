"""Tests for workspace write tools (WriteFileTool, ApplyPatchTool) and ToolGateway enforcement."""

import uuid

import pytest

from app.harness.context import ExecutionContext
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.tools.gateway import ApprovedPlan, ToolGateway
from app.tools.registry import ToolRegistry
from app.tools.workspace import build_workspace_tools


@pytest.fixture
def sandbox_dir(tmp_path):
    sbx = tmp_path / "sandbox"
    sbx.mkdir(parents=True, exist_ok=True)
    return sbx


@pytest.fixture
async def setup_agent_context(db_session, sandbox_dir):
    user = User(id=uuid.uuid4(), email=f"agent-{uuid.uuid4().hex[:6]}@example.com", full_name="Agent User", hashed_password="pw")
    db_session.add(user)
    org = Organization(id=uuid.uuid4(), name="Agent Org", slug=f"agent-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    project = Project(
        id=uuid.uuid4(),
        name="Agent Project",
        slug=f"proj-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
    )
    db_session.add(project)

    run = AgentRun(
        id=uuid.uuid4(),
        organization_id=org.id,
        project_id=project.id,
        agent_name="coding_agent",
        agent_version="1.0.0",
        status=AgentRunStatus.RUNNING,
    )
    db_session.add(run)
    await db_session.commit()

    context = ExecutionContext(
        organization_id=org.id,
        project_id=project.id,
        repository_id=None,
        environment="test",
        agent_name="coding_agent",
        agent_version="1.0.0",
        capabilities=frozenset({"repository.read", "workspace.write"}),
        agent_run_id=run.id,
        workspace_reference=str(sandbox_dir),
    )
    return org, project, run, context


@pytest.mark.asyncio
async def test_write_file_without_approved_plan_denied(db_session, setup_agent_context, sandbox_dir):
    _, _, run, context = setup_agent_context
    registry = ToolRegistry()
    tools = build_workspace_tools(resolve_path=lambda ctx: sandbox_dir)
    for t in tools:
        registry.register(t)

    gateway = ToolGateway(registry)

    # Calling write tool with approved_plan=None
    result = await gateway.execute(
        db_session,
        run,
        context,
        tool_name="write_file",
        arguments={"path": "app/test.txt", "content": "hello"},
        approved_plan=None,
    )
    assert result.denied is True
    assert "requires an approved plan" in (result.error or "")


@pytest.mark.asyncio
async def test_write_file_without_write_capability_denied(db_session, setup_agent_context, sandbox_dir):
    org, project, run, _ = setup_agent_context
    # Context without workspace.write
    read_only_context = ExecutionContext(
        organization_id=org.id,
        project_id=project.id,
        repository_id=None,
        environment="test",
        agent_name="coding_agent",
        agent_version="1.0.0",
        capabilities=frozenset({"repository.read"}),
        agent_run_id=run.id,
        workspace_reference=str(sandbox_dir),
    )
    registry = ToolRegistry()
    for t in build_workspace_tools(resolve_path=lambda ctx: sandbox_dir):
        registry.register(t)
    gateway = ToolGateway(registry)
    approved_plan = ApprovedPlan(plan_id="plan-1", approved_by=uuid.uuid4())

    result = await gateway.execute(
        db_session,
        run,
        read_only_context,
        tool_name="write_file",
        arguments={"path": "app/test.txt", "content": "hello"},
        approved_plan=approved_plan,
    )
    assert result.denied is True
    assert "lacks the 'workspace.write' capability" in (result.error or "")


@pytest.mark.asyncio
async def test_write_file_and_apply_patch_success(db_session, setup_agent_context, sandbox_dir):
    _, _, run, context = setup_agent_context
    registry = ToolRegistry()
    for t in build_workspace_tools(resolve_path=lambda ctx: sandbox_dir):
        registry.register(t)
    gateway = ToolGateway(registry)
    approved_plan = ApprovedPlan(plan_id="plan-1", approved_by=uuid.uuid4())

    # 1. Write file
    initial_content = "<html>\n  <body>\n    <h1>Home</h1>\n  </body>\n</html>"
    write_res = await gateway.execute(
        db_session,
        run,
        context,
        tool_name="write_file",
        arguments={"path": "app/index.html", "content": initial_content},
        approved_plan=approved_plan,
    )
    assert not write_res.is_error
    assert write_res.output["status"] == "written"
    assert (sandbox_dir / "app" / "index.html").exists()

    # 2. Apply patch
    patch_res = await gateway.execute(
        db_session,
        run,
        context,
        tool_name="apply_patch",
        arguments={
            "path": "app/index.html",
            "target": "<h1>Home</h1>",
            "replacement": "<h1>Home</h1>\n    <!-- Fussion Widget -->",
        },
        approved_plan=approved_plan,
    )
    assert not patch_res.is_error
    assert patch_res.output["status"] == "patched"

    updated = (sandbox_dir / "app" / "index.html").read_text(encoding="utf-8")
    assert "<!-- Fussion Widget -->" in updated


@pytest.mark.asyncio
async def test_workspace_tools_reject_path_traversal(db_session, setup_agent_context, sandbox_dir):
    _, _, run, context = setup_agent_context
    registry = ToolRegistry()
    for t in build_workspace_tools(resolve_path=lambda ctx: sandbox_dir):
        registry.register(t)
    gateway = ToolGateway(registry)
    approved_plan = ApprovedPlan(plan_id="plan-1", approved_by=uuid.uuid4())

    res = await gateway.execute(
        db_session,
        run,
        context,
        tool_name="write_file",
        arguments={"path": "../../../outside.txt", "content": "evil"},
        approved_plan=approved_plan,
    )
    assert res.is_error
    assert "Security refusal" in (res.error or "") or "Sandbox" in (res.error or "")


@pytest.mark.asyncio
async def test_workspace_tools_reject_protected_files(db_session, setup_agent_context, sandbox_dir):
    _, _, run, context = setup_agent_context
    registry = ToolRegistry()
    for t in build_workspace_tools(resolve_path=lambda ctx: sandbox_dir):
        registry.register(t)
    gateway = ToolGateway(registry)
    approved_plan = ApprovedPlan(plan_id="plan-1", approved_by=uuid.uuid4())

    res_env = await gateway.execute(
        db_session,
        run,
        context,
        tool_name="write_file",
        arguments={"path": ".env.production", "content": "SECRET=123"},
        approved_plan=approved_plan,
    )
    assert res_env.is_error
    assert "protected path" in res_env.error
