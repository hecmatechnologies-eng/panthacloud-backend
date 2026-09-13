"""Step C · C8 — the WebsiteAnalyst (AGENT-ARCHITECTURE §3.2).

The deterministic pre-analysis, the declarative agent, and the run that produces a `WebsiteProfile`
(or declines). The eval corpus that gates this is C9.
"""

import json
import shutil
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.registry import register_default_agents
from app.agents.website_analyst import WEBSITE_ANALYST
from app.agents.website_profile import IntegrationCandidate, WebsiteProfile
from app.core.database import get_session_factory
from app.evals.runner import harness_analyzer
from app.harness.context import ExecutionContext
from app.harness.runner import AgentRunResult
from app.llm.gateway import ModelGateway
from app.llm.providers.fake import FakeModelProvider
from app.models.agent_run import AgentRun, AgentRunStatus
from app.services.analysis.analyst import analyze_repository, build_prompt
from app.services.analysis.pre_analysis import pre_analyze
from app.services.repository.reader import LocalWorkspaceReader
from app.tools.gateway import ToolGateway
from app.tools.registry import ToolRegistry
from app.tools.repository import register_repository_tools

READ_CAP = "repository.read"


def _temp_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="c8-repo-"))
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def nextjs_repo() -> Path:
    root = _temp_repo(
        {
            "package.json": json.dumps({"dependencies": {"next": "14.0.0", "react": "18"}}),
            "app/layout.tsx": "export default function Root({ children }) { return children; }",
        }
    )
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ============================================================
# 1. The profile contract
# ============================================================


def test_profile_defaults_to_no_candidates_and_no_refusal() -> None:
    profile = WebsiteProfile()
    assert profile.integration_candidates == []
    assert profile.unsupported_reason is None


def test_candidates_are_ranked_records() -> None:
    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[
            IntegrationCandidate(path="app/layout.tsx", confidence=0.9, reason="root layout"),
            IntegrationCandidate(path="src/app/layout.tsx", confidence=0.4, reason="alt layout"),
        ],
    )
    assert profile.integration_candidates[0].path == "app/layout.tsx"


# ============================================================
# 2. Deterministic pre-analysis
# ============================================================


def test_pre_analysis_matches_nextjs(nextjs_repo: Path) -> None:
    pre = pre_analyze(nextjs_repo)
    assert [match.skill_id for match in pre.skills] == ["nextjs-app-router"]
    assert "app/layout.tsx" in pre.entry_point_candidates
    assert "package.json" in pre.manifests
    assert "middleware.ts" in pre.protected_paths


def test_pre_analysis_matches_static_html() -> None:
    root = _temp_repo({"index.html": "<html><body>hi</body></html>"})
    try:
        pre = pre_analyze(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert [match.skill_id for match in pre.skills] == ["generic-html"]


def test_pre_analysis_of_an_unrecognised_repo_is_empty() -> None:
    root = _temp_repo({"README.md": "just docs"})
    try:
        pre = pre_analyze(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert pre.skills == []


def test_prompt_carries_the_pre_analysis_as_data(nextjs_repo: Path) -> None:
    prompt = build_prompt(pre_analyze(nextjs_repo))
    assert "nextjs-app-router" in prompt
    assert "DETERMINISTIC PRE-ANALYSIS" in prompt
    assert "data, not instructions" in prompt


# ============================================================
# 3. The agent declaration
# ============================================================


def test_analyst_is_declarative() -> None:
    assert WEBSITE_ANALYST.name == "website_analyst"
    assert WEBSITE_ANALYST.capabilities == frozenset({READ_CAP})
    assert WEBSITE_ANALYST.tools == ("read_tree", "read_file", "search_code")
    assert WEBSITE_ANALYST.output_schema is WebsiteProfile
    assert WEBSITE_ANALYST.budget.cost_usd == Decimal("0.50")


def test_default_agents_register_the_analyst() -> None:
    from app.agents.registry import registry as global_registry

    register_default_agents()
    register_default_agents()  # idempotent
    assert global_registry.get("website_analyst", "1.0.0") is WEBSITE_ANALYST


# ============================================================
# 4. The run produces a profile
# ============================================================


class _FakeAnalystRunner:
    def __init__(self, profile: WebsiteProfile) -> None:
        self._profile = profile

    async def run(
        self, definition, context, *, prompt, tools=(), tool_executor=None, usage_recorder=None
    ):
        result = AgentRunResult(
            output=self._profile,
            text=None,
            input_tokens=100,
            output_tokens=50,
            provider="fake",
            model_id="gemini-2.5-flash",
            model_version_reported="v1",
        )
        if usage_recorder is not None:
            await usage_recorder(result)
        return result


async def _tenant(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
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
    org_id = orgs.json()[0]["id"]
    proj = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"{name} Proj", "slug": f"{name.lower()}-proj"},
    )
    assert proj.status_code == 201
    return org_id, proj.json()["id"]


@pytest.mark.asyncio
async def test_analyze_repository_returns_the_profile(
    client: AsyncClient, nextjs_repo: Path
) -> None:
    org_id, proj_id = await _tenant(client, "c8_owner@example.com", "C8Owner")
    context = ExecutionContext(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        repository_id=None,
        environment="test",
        agent_name="website_analyst",
        agent_version="1.0.0",
        capabilities=frozenset({READ_CAP}),
        commit_sha="a" * 40,
    )
    registry = ToolRegistry()
    register_repository_tools(registry, lambda _ctx: LocalWorkspaceReader(nextjs_repo))
    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[
            IntegrationCandidate(path="app/layout.tsx", confidence=0.9, reason="root layout")
        ],
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        run, returned = await analyze_repository(
            db,
            context=context,
            repo_root=nextjs_repo,
            runner=_FakeAnalystRunner(profile),
            gateway=ModelGateway(FakeModelProvider()),
            tool_gateway=ToolGateway(registry),
            registry=registry,
        )
        await db.commit()
        run_id = run.id

    assert returned == profile
    async with session_factory() as db:
        stored = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
    assert stored.status == AgentRunStatus.COMPLETED
    assert stored.agent_name == "website_analyst"
    # FR-089: the run records which skill version it used.
    assert stored.skill_versions == {"nextjs-app-router": "1.0.0"}


@pytest.mark.asyncio
async def test_the_eval_harness_analyzer_drives_the_agent(
    client: AsyncClient, nextjs_repo: Path
) -> None:
    """The eval seam runs the real pipeline, not just the model-free analyzer."""
    org_id, proj_id = await _tenant(client, "c8_seam@example.com", "C8Seam")
    context = ExecutionContext(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        repository_id=None,
        environment="test",
        agent_name="website_analyst",
        agent_version="1.0.0",
        capabilities=frozenset({READ_CAP}),
    )
    registry = ToolRegistry()
    register_repository_tools(registry, lambda _ctx: LocalWorkspaceReader(nextjs_repo))
    profile = WebsiteProfile(framework_skill_id="nextjs-app-router")

    session_factory = get_session_factory()
    async with session_factory() as db:
        analyzer = harness_analyzer(
            db=db,
            context=context,
            runner=_FakeAnalystRunner(profile),
            gateway=ModelGateway(FakeModelProvider()),
            tool_gateway=ToolGateway(registry),
            registry=registry,
        )
        result = await analyzer(nextjs_repo)
        await db.commit()

    assert result.profile == profile
