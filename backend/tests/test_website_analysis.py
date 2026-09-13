"""Step C · C10 — website analysis wiring (MVP acceptance #4).

The analyst runs against a cloned repository, the detected profile is persisted keyed to the commit
SHA, and it is served back. Cloning and the model are stubbed; the wiring, persistence and tenancy
are real.
"""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.website_profile import IntegrationCandidate, WebsiteProfile
from app.core.database import get_session_factory
from app.harness.runner import AgentRunResult
from app.llm.gateway import ModelGateway
from app.llm.providers.fake import FakeModelProvider
from app.models.website_analysis import WebsiteAnalysis

ANALYZE = "analyze"
ANALYSIS = "analysis"
COMMIT_SHA = "a" * 40


class _FakeRunner:
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


def _stub_clone(profile: WebsiteProfile):
    async def fake_clone(_url, _branch, workspace_path):
        (workspace_path / "app").mkdir(parents=True, exist_ok=True)
        (workspace_path / "app" / "layout.tsx").write_text("export default null;", encoding="utf-8")
        (workspace_path / "package.json").write_text(
            json.dumps({"dependencies": {"next": "14.0.0"}}), encoding="utf-8"
        )
        return COMMIT_SHA

    return fake_clone


def _stub_analysis(monkeypatch: pytest.MonkeyPatch, profile: WebsiteProfile) -> None:
    """Stub cloning and the model, leaving the wiring, persistence and selection real."""
    monkeypatch.setattr(
        "app.services.analysis.analysis_service.clone_repository", _stub_clone(profile)
    )
    monkeypatch.setattr(
        "app.services.analysis.analysis_service.PydanticAIAgentRunner",
        lambda: _FakeRunner(profile),
    )
    monkeypatch.setattr(
        "app.services.analysis.analysis_service.get_model_gateway",
        lambda: ModelGateway(FakeModelProvider()),
    )


async def _tenant(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
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
    proj_id = proj.json()["id"]
    integration = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"repository_owner": "acme", "repository_name": "store"},
    )
    assert integration.status_code == 201
    return token, org_id, proj_id


def _integration_url(org_id: str, proj_id: str) -> str:
    return f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"


@pytest.mark.asyncio
async def test_analysis_endpoint_runs_and_persists(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token, org_id, proj_id = await _tenant(client, "c10_owner@example.com", "C10Owner")
    hdr = {"Authorization": f"Bearer {token}"}
    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        router="app",
        integration_candidates=[
            IntegrationCandidate(path="app/layout.tsx", confidence=0.9, reason="root layout")
        ],
        design_tokens={"primary_color": "#111111"},
        protected_paths=["middleware.ts"],
    )
    monkeypatch.setattr(
        "app.services.analysis.analysis_service.clone_repository", _stub_clone(profile)
    )
    monkeypatch.setattr(
        "app.services.analysis.analysis_service.PydanticAIAgentRunner",
        lambda: _FakeRunner(profile),
    )
    monkeypatch.setattr(
        "app.services.analysis.analysis_service.get_model_gateway",
        lambda: ModelGateway(FakeModelProvider()),
    )

    resp = await client.post(f"{_integration_url(org_id, proj_id)}/{ANALYZE}", headers=hdr)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["framework_skill_id"] == "nextjs-app-router"
    assert body["commit_sha"] == COMMIT_SHA
    assert body["integration_candidates"][0]["path"] == "app/layout.tsx"
    assert body["unsupported_reason"] is None

    latest = await client.get(f"{_integration_url(org_id, proj_id)}/{ANALYSIS}", headers=hdr)
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_analysis_configures_the_integration(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C11: what was detected becomes the integration's configuration, so the plan uses it."""
    token, org_id, proj_id = await _tenant(client, "c11_owner@example.com", "C11Owner")
    hdr = {"Authorization": f"Bearer {token}"}
    profile = WebsiteProfile(
        framework_skill_id="generic-html",
        integration_candidates=[
            IntegrationCandidate(path="index.html", confidence=0.9, reason="static entry")
        ],
    )
    _stub_analysis(monkeypatch, profile)

    resp = await client.post(f"{_integration_url(org_id, proj_id)}/{ANALYZE}", headers=hdr)
    assert resp.status_code == 200, resp.text

    # The integration defaults are nextjs-app-router / app/layout.tsx; the analysis overrides both.
    configured = (await client.get(_integration_url(org_id, proj_id), headers=hdr)).json()
    assert configured["framework_skill_id"] == "generic-html"
    assert configured["widget_target_path"] == "index.html"


@pytest.mark.asyncio
async def test_analysis_below_threshold_leaves_the_integration_unconfigured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A weak candidate is not a decision: a human chooses in the Studio (C11)."""
    token, org_id, proj_id = await _tenant(client, "c11_low@example.com", "C11Low")
    hdr = {"Authorization": f"Bearer {token}"}
    profile = WebsiteProfile(
        framework_skill_id="generic-html",
        integration_candidates=[
            IntegrationCandidate(path="index.html", confidence=0.2, reason="uncertain")
        ],
    )
    _stub_analysis(monkeypatch, profile)

    resp = await client.post(f"{_integration_url(org_id, proj_id)}/{ANALYZE}", headers=hdr)
    assert resp.status_code == 200, resp.text

    configured = (await client.get(_integration_url(org_id, proj_id), headers=hdr)).json()
    assert configured["framework_skill_id"] == "nextjs-app-router"
    assert configured["widget_target_path"] == "app/layout.tsx"


@pytest.mark.asyncio
async def test_unsupported_analysis_refuses_plan_and_run(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance #10: an unanalysable repository is refused with its reason, not integrated."""
    token, org_id, proj_id = await _tenant(client, "c11_refuse@example.com", "C11Refuse")
    hdr = {"Authorization": f"Bearer {token}"}
    profile = WebsiteProfile(unsupported_reason="Not a website Fussion can integrate.")
    _stub_analysis(monkeypatch, profile)

    resp = await client.post(f"{_integration_url(org_id, proj_id)}/{ANALYZE}", headers=hdr)
    assert resp.status_code == 200, resp.text
    assert resp.json()["unsupported_reason"] is not None

    plan = await client.get(f"{_integration_url(org_id, proj_id)}/plan", headers=hdr)
    assert plan.status_code == 422
    assert "cannot be integrated" in plan.json()["detail"]

    run = await client.post(f"{_integration_url(org_id, proj_id)}/runs", headers=hdr)
    assert run.status_code == 422

    # Refused before any work: no run was recorded for the refused repository.
    from app.models.website_integration import IntegrationRun, WebsiteIntegration

    session_factory = get_session_factory()
    async with session_factory() as db:
        integration = (
            await db.execute(
                select(WebsiteIntegration).where(
                    WebsiteIntegration.project_id == uuid.UUID(proj_id)
                )
            )
        ).scalar_one()
        runs = (
            await db.execute(
                select(IntegrationRun).where(IntegrationRun.integration_id == integration.id)
            )
        ).scalars().all()
    assert runs == []


@pytest.mark.asyncio
async def test_re_analysis_below_threshold_keeps_the_existing_configuration(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Declining to auto-configure is non-destructive: it never clobbers a working configuration."""
    token, org_id, proj_id = await _tenant(client, "c11_keep@example.com", "C11Keep")
    hdr = {"Authorization": f"Bearer {token}"}

    good = WebsiteProfile(
        framework_skill_id="generic-html",
        integration_candidates=[
            IntegrationCandidate(path="index.html", confidence=0.9, reason="static entry")
        ],
    )
    _stub_analysis(monkeypatch, good)
    first = await client.post(f"{_integration_url(org_id, proj_id)}/{ANALYZE}", headers=hdr)
    assert first.status_code == 200, first.text

    weak = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[
            IntegrationCandidate(path="app/layout.tsx", confidence=0.1, reason="uncertain")
        ],
    )
    _stub_analysis(monkeypatch, weak)
    second = await client.post(f"{_integration_url(org_id, proj_id)}/{ANALYZE}", headers=hdr)
    assert second.status_code == 200, second.text

    configured = (await client.get(_integration_url(org_id, proj_id), headers=hdr)).json()
    assert configured["framework_skill_id"] == "generic-html"
    assert configured["widget_target_path"] == "index.html"


@pytest.mark.asyncio
async def test_analysis_is_tenant_scoped(client: AsyncClient) -> None:
    _, org_id, proj_id = await _tenant(client, "c10_a@example.com", "C10A")
    other_token, _, _ = await _tenant(client, "c10_b@example.com", "C10B")

    resp = await client.get(
        f"{_integration_url(org_id, proj_id)}/{ANALYSIS}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analysis_is_deleted_with_the_integration(client: AsyncClient) -> None:
    token, org_id, proj_id = await _tenant(client, "c10_cascade@example.com", "C10Cascade")
    hdr = {"Authorization": f"Bearer {token}"}

    from app.models.website_integration import WebsiteIntegration

    session_factory = get_session_factory()
    async with session_factory() as db:
        integration = (
            await db.execute(
                select(WebsiteIntegration).where(
                    WebsiteIntegration.project_id == uuid.UUID(proj_id)
                )
            )
        ).scalar_one()
        db.add(
            WebsiteAnalysis(
                integration_id=integration.id,
                commit_sha=COMMIT_SHA,
                framework_skill_id="generic-html",
            )
        )
        await db.commit()

    assert (await client.delete(_integration_url(org_id, proj_id), headers=hdr)).status_code == 204
    async with session_factory() as db:
        assert (await db.execute(select(WebsiteAnalysis))).scalars().all() == []
