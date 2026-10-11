"""Tests for the autonomous CodingAgent (Step D) and minified widget bundle delivery."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.agents.coding_agent import CodingAgentOutput, GeneratedFileRecord
from app.agents.registry import get_agent, register_default_agents
from app.harness.context import ExecutionContext
from app.harness.runner import AgentRunResult
from app.models.organization import Organization
from app.models.project import Project
from app.models.website_integration import WebsiteIntegration, WebsiteIntegrationStatus
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.coder import execute_coding_agent
from app.services.integration.sandbox import LocalWorkspaceProvider
from app.tools.gateway import ApprovedPlan, ToolGateway
from app.tools.registry import ToolRegistry


def test_coding_agent_registered():
    register_default_agents()
    agent = get_agent("coding_agent", "1.0.0")
    assert agent.name == "coding_agent"
    assert "workspace.write" in agent.capabilities
    assert "repository.read" in agent.capabilities
    assert "write_file" in agent.tools
    assert "apply_patch" in agent.tools


@pytest.mark.asyncio
async def test_coding_agent_execution_and_repair_loop(db_session, tmp_path):
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    ws_provider = LocalWorkspaceProvider()

    org = Organization(id=uuid.uuid4(), name="Agent Org", slug=f"agent-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    project = Project(
        id=uuid.uuid4(),
        name="Agent Project",
        slug=f"proj-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
    )
    db_session.add(project)

    integration = WebsiteIntegration(
        id=uuid.uuid4(),
        project_id=project.id,
        repository_owner="testowner",
        repository_name="testrepo",
        default_branch="main",
        framework_skill_id="nextjs-app-router",
        widget_target_path="app/layout.tsx",
        status=WebsiteIntegrationStatus.CONNECTED,
    )
    db_session.add(integration)
    await db_session.commit()

    context = ExecutionContext(
        organization_id=org.id,
        project_id=project.id,
        repository_id=None,
        environment="test",
        agent_name="coding_agent",
        agent_version="1.0.0",
        capabilities=frozenset({"repository.read", "workspace.write"}),
        integration_id=integration.id,
        workspace_reference=str(sandbox_dir),
    )
    approved_plan = ApprovedPlan(plan_id="plan-test", approved_by=uuid.uuid4())

    plan = IntegrationPlanPayload(
        framework_skill_id="nextjs-app-router",
        files_to_create=[],
        files_to_modify=["app/layout.tsx"],
        target_status="exists",
    )

    original_target = (
        "export default function RootLayout({ children }: { children: React.ReactNode }) {\n"
        "  return (\n"
        "    <html lang=\"en\">\n"
        "      <body>{children}</body>\n"
        "    </html>\n"
        "  );\n"
        "}\n"
    )
    ws_provider.write_file(sandbox_dir, "app/layout.tsx", original_target)

    from app.services.integration.artifacts import patch_react_layout
    valid_integrated_content = patch_react_layout(original_target)

    # Mock runner that writes the valid file into sandbox when executed
    mock_runner = AsyncMock()

    async def fake_run(*args, **kwargs):
        # Write the integrated file into sandbox
        ws_provider.write_file(sandbox_dir, "app/layout.tsx", valid_integrated_content)
        output = CodingAgentOutput(
            summary="Injected Fussion widget into app/layout.tsx",
            files=[GeneratedFileRecord(path="app/layout.tsx", action="modify", summary="Added widget script")],
            validation_passed=True,
        )
        res = AgentRunResult(
            output=output,
            text=None,
            input_tokens=100,
            output_tokens=50,
            provider="test",
            model_id="mock-model",
            model_version_reported="1.0",
        )
        on_result = kwargs.get("on_result")
        if on_result:
            await on_result(res)
        return res

    mock_runner.run = AsyncMock(side_effect=fake_run)
    mock_gateway = AsyncMock()

    registry = ToolRegistry()
    tool_gateway = ToolGateway(registry)

    _run, generated_files = await execute_coding_agent(
        db_session,
        context=context,
        plan=plan,
        approved_plan=approved_plan,
        sandbox_path=sandbox_dir,
        integration=integration,
        assistant_data={"brand_color": "#4338ca", "position": "BOTTOM_RIGHT"},
        original_target=original_target,
        runner=mock_runner,
        gateway=mock_gateway,
        tool_gateway=tool_gateway,
        registry=registry,
        workspace_provider=ws_provider,
    )

    assert "app/layout.tsx" in generated_files
    assert "FussionAssistant" in generated_files["app/layout.tsx"]


# ============================================================
# The pipeline wiring around the agent (standards-alignment.md G8)
# ============================================================


def test_coding_agent_switch_is_a_real_setting():
    """It was previously read with getattr(settings, ..., True) but never declared, so the
    switch was dead and only an APP_ENV check inside the pipeline disabled the agent."""
    from app.core.config import Settings

    assert "ENABLE_CODING_AGENT" in Settings.model_fields


def test_coding_agent_is_off_by_default_in_the_suite():
    from app.core.config import settings

    assert settings.ENABLE_CODING_AGENT is False


def test_pipeline_no_longer_disables_the_agent_by_app_env():
    """The blunt APP_ENV check hid the entire wiring from the suite. The explicit setting
    replaces it, so tests opt in rather than being silently excluded."""
    import inspect

    from app.services.integration import pipeline

    source = inspect.getsource(pipeline)
    assert 'settings.APP_ENV != "test"' not in source
    assert "settings.ENABLE_CODING_AGENT" in source


@pytest.mark.asyncio
async def test_the_repair_loop_is_bounded_and_reports_its_failure(db_session, tmp_path):
    """ASI08: the repair turn re-enters the same loop with the same tools. A run that cannot
    converge must stop and say so rather than oscillating silently."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    ws_provider = LocalWorkspaceProvider()

    org = Organization(id=uuid.uuid4(), name="Repair Org", slug=f"repair-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Repair Project",
        slug=f"repair-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(project)
    await db_session.flush()

    integration = WebsiteIntegration(
        id=uuid.uuid4(),
        project_id=project.id,
        provider="github",
        repository_owner="acme",
        repository_name="site",
        default_branch="main",
        framework_skill_id="nextjs-app-router",
        website_root_dir="/",
        widget_target_path="app/layout.tsx",
        status=WebsiteIntegrationStatus.GENERATING,
    )
    db_session.add(integration)
    await db_session.flush()

    context = ExecutionContext(
        organization_id=org.id,
        project_id=project.id,
        repository_id=None,
        environment="test",
        agent_name="coding_agent",
        agent_version="1.0.0",
        capabilities=frozenset({"repository.read", "workspace.write"}),
    )
    plan = IntegrationPlanPayload.model_validate(
        {
            "framework_skill_id": "nextjs-app-router",
            "widget_target_path": "app/layout.tsx",
            "files_to_create": ["components/FussionWidget.tsx"],
            "files_to_modify": ["app/layout.tsx"],
            "target_status": "exists",
        }
    )
    approved_plan = ApprovedPlan(plan_id="p1", approved_by=org.id)
    ws_provider.write_file(sandbox_dir, "app/layout.tsx", "export default function App() {}")

    mock_runner = AsyncMock()

    async def never_converges(*args, **kwargs):
        # Always writes something the validator rejects, so the repair turn also "fails" to fix it.
        ws_provider.write_file(sandbox_dir, "app/layout.tsx", "<<< not valid >>>")
        res = AgentRunResult(
            output=CodingAgentOutput(summary="attempted", files=[], validation_passed=False),
            text=None,
            input_tokens=10,
            output_tokens=5,
            provider="test",
            model_id="mock-model",
            model_version_reported="1.0",
        )
        on_result = kwargs.get("on_result")
        if on_result:
            await on_result(res)
        return res

    mock_runner.run = AsyncMock(side_effect=never_converges)

    with pytest.raises(Exception) as caught:
        await execute_coding_agent(
            db_session,
            context=context,
            plan=plan,
            approved_plan=approved_plan,
            sandbox_path=sandbox_dir,
            integration=integration,
            assistant_data={"brand_color": "#4338ca", "position": "BOTTOM_RIGHT"},
            original_target="export default function App() {}",
            runner=mock_runner,
            gateway=AsyncMock(),
            tool_gateway=ToolGateway(ToolRegistry()),
            registry=ToolRegistry(),
            workspace_provider=ws_provider,
        )

    # It must surface rather than returning a bad integration as success.
    assert "validation" in str(caught.value).lower()
    assert mock_runner.run.await_count == 2, "expected exactly one repair turn, not a loop"


@pytest.mark.asyncio
async def test_public_widget_serves_minified_script(client):
    resp = await client.get("/api/v1/public/widget.js")
    assert resp.status_code == 200
    assert "application/javascript" in resp.headers["content-type"]
    assert "ETag" in resp.headers
    assert "max-age=300" in resp.headers.get("Cache-Control", "")
    content = resp.text
    assert "use strict" in content
    assert "data-fussion-key" in content
