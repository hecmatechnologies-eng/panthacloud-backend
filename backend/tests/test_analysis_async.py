"""Tests for asynchronous repository analysis (HTTP 202 Accepted and job polling)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.agents.website_profile import IntegrationCandidate, WebsiteProfile
from app.llm.gateway import ModelGateway
from app.llm.providers.fake import FakeModelProvider


class _FakeRunner:
    def __init__(self, profile: WebsiteProfile) -> None:
        self._profile = profile

    async def run(
        self, definition, context, *, prompt, tools=(), tool_executor=None, usage_recorder=None
    ):
        from app.harness.runner import AgentRunResult

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
        return "b" * 40

    return fake_clone


async def _setup_tenant_and_integration(client: AsyncClient, name: str) -> tuple[str, str, str, str]:
    email = f"{name.lower()}@example.com"
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
    orgs = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
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
    int_id = integration.json()["id"]
    return token, org_id, proj_id, int_id


@pytest.mark.asyncio
async def test_async_analysis_endpoint_returns_202_when_queued(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    token, org_id, proj_id, _int_id = await _setup_tenant_and_integration(client, "AsyncUser")
    headers = {"Authorization": f"Bearer {token}"}

    fake_job_id = f"test-job-{uuid.uuid4().hex[:8]}"

    # Mock enqueue_analysis to return a valid job id
    with patch("app.jobs.queue.enqueue_analysis", new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = fake_job_id

        resp = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/analyze?async=true",
            headers=headers,
        )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "queued"
        assert body["job_id"] == fake_job_id
        assert fake_job_id in body["poll_url"]
        assert "events/stream" in body["events_url"]


@pytest.mark.asyncio
async def test_async_analysis_job_polling_endpoint(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    token, org_id, proj_id, _int_id = await _setup_tenant_and_integration(client, "PollUser")
    headers = {"Authorization": f"Bearer {token}"}

    fake_job_id = f"poll-job-{uuid.uuid4().hex[:8]}"

    # Mock get_job_info to return in-progress status
    with patch("app.jobs.queue.get_job_info", new_callable=AsyncMock) as mock_info:
        mock_info.return_value = {"job_id": fake_job_id, "status": "in_progress"}

        poll_res = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/analyze/jobs/{fake_job_id}",
            headers=headers,
        )

        assert poll_res.status_code == 200
        body = poll_res.json()
        assert body["status"] == "in_progress"
        assert body["job_id"] == fake_job_id


@pytest.mark.asyncio
async def test_sync_fallback_when_async_unconfigured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    token, org_id, proj_id, _int_id = await _setup_tenant_and_integration(client, "SyncFallbackUser")
    headers = {"Authorization": f"Bearer {token}"}

    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        router="app",
        integration_candidates=[
            IntegrationCandidate(path="app/layout.tsx", confidence=0.9, reason="root layout")
        ],
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

    # When async=false, executes synchronously and returns 200 OK
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/analyze",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["framework_skill_id"] == "nextjs-app-router"
