"""Step C closeout — the run-cockpit read endpoints (FR-073, FR-089, FR-090, FR-116).

The control plane serves what the harness persisted: an agent run with its ordered tool-call log,
and the project's model-usage ledger. Cross-tenant access is a 404, never a 403.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.database import get_session_factory
from app.models.agent_run import AgentRun, AgentRunStatus, AgentToolCall
from app.models.model_usage import ModelUsage


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
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
    data = resp.json()
    token = data["access_token"]
    orgs_resp = await client.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return token, data["user"]["id"], orgs_resp.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, name: str, slug: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": slug},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def seed_run(
    org_id: str, project_id: str, *, cost: str = "0.002000", integration_id: str | None = None
) -> str:
    session_factory = get_session_factory()
    async with session_factory() as db:
        run = AgentRun(
            organization_id=uuid.UUID(org_id),
            project_id=uuid.UUID(project_id),
            agent_name="website_analyst",
            agent_version="1.0.0",
            status=AgentRunStatus.COMPLETED,
            current_step="report",
            prompt_hash="abc123",
            model_id="gemini-2.5-flash",
            model_version_reported="gemini-2.5-flash-001",
            skill_versions={"nextjs-app-router": "1.0.0"},
            budget={"tool_calls": 10, "tokens": 1000, "seconds": 30, "cost_usd": "0.10"},
            tokens_used=150,
            cost_usd=Decimal(cost),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        db.add_all(
            [
                AgentToolCall(
                    agent_run_id=run.id,
                    sequence=1,
                    tool_name="read_tree",
                    arguments={"depth": 2},
                    outcome="ok",
                    duration_ms=12,
                ),
                AgentToolCall(
                    agent_run_id=run.id,
                    sequence=2,
                    tool_name="read_file",
                    arguments={"path": "app/layout.tsx"},
                    outcome="ok",
                    duration_ms=4,
                ),
            ]
        )
        db.add(
            ModelUsage(
                organization_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                integration_id=uuid.UUID(integration_id) if integration_id else None,
                provider="gemini",
                model="gemini-2.5-flash",
                input_tokens=100,
                output_tokens=50,
                estimated_cost_usd=Decimal(cost),
                latency_ms=900,
            )
        )
        await db.commit()
        return str(run.id)


@pytest.mark.asyncio
async def test_agent_run_list_and_detail_expose_the_tool_log(client: AsyncClient) -> None:
    token, _uid, org_id = await register_user(client, "runs@example.com", "RunsUser")
    proj_id = await create_project(client, token, org_id, "Runs Project", "runs-project")
    run_id = await seed_run(org_id, proj_id)
    hdr = {"Authorization": f"Bearer {token}"}

    listed = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/agent-runs", headers=hdr
    )
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["id"] == run_id
    assert body[0]["model_id"] == "gemini-2.5-flash"

    detail = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/agent-runs/{run_id}", headers=hdr
    )
    assert detail.status_code == 200
    run = detail.json()
    assert run["prompt_hash"] == "abc123"
    assert [call["sequence"] for call in run["tool_calls"]] == [1, 2]
    assert run["tool_calls"][0]["tool_name"] == "read_tree"


@pytest.mark.asyncio
async def test_agent_run_is_not_reachable_across_tenants(client: AsyncClient) -> None:
    token_a, _uid_a, org_a = await register_user(client, "runs-a@example.com", "RunsA")
    proj_a = await create_project(client, token_a, org_a, "A Project", "a-project")
    run_a = await seed_run(org_a, proj_a)

    token_b, _uid_b, org_b = await register_user(client, "runs-b@example.com", "RunsB")
    proj_b = await create_project(client, token_b, org_b, "B Project", "b-project")
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    # B asking for A's run under A's own org/project path is a 404, not a 403.
    resp = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/agent-runs/{run_a}", headers=hdr_b
    )
    assert resp.status_code == 404

    # And B's own project shows nothing of A's.
    own = await client.get(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/agent-runs", headers=hdr_b
    )
    assert own.status_code == 200
    assert own.json() == []


@pytest.mark.asyncio
async def test_project_usage_summarises_cost_by_model(client: AsyncClient) -> None:
    token, _uid, org_id = await register_user(client, "usage@example.com", "UsageUser")
    proj_id = await create_project(client, token, org_id, "Usage Project", "usage-project")
    await seed_run(org_id, proj_id, cost="0.002000")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_calls"] == 1
    assert summary["input_tokens"] == 100
    assert summary["output_tokens"] == 50
    assert Decimal(str(summary["cost_usd"])) == Decimal("0.002000")
    assert len(summary["by_model"]) == 1
    assert summary["by_model"][0]["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_org_budget_status_reports_month_spend(client: AsyncClient) -> None:
    token, _uid, org_id = await register_user(client, "budget@example.com", "BudgetUser")
    proj_id = await create_project(client, token, org_id, "Budget Project", "budget-project")
    await seed_run(org_id, proj_id, cost="0.002000")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/usage/budget",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Default limit is $10 and the seeded spend is tiny, so the tenant is comfortably "ok".
    assert body["state"] == "ok"
    assert Decimal(str(body["month_spend_usd"])) == Decimal("0.002000")
    assert Decimal(str(body["limit_usd"])) == Decimal("10.0")
    assert 0 <= float(body["fraction"]) < 1


@pytest.mark.asyncio
async def test_usage_can_be_filtered_by_integration(client: AsyncClient) -> None:
    token, _uid, org_id = await register_user(client, "attrib@example.com", "AttribUser")
    proj_id = await create_project(client, token, org_id, "Attrib Project", "attrib-project")
    integration_id = str(uuid.uuid4())
    await seed_run(org_id, proj_id, cost="0.002000", integration_id=integration_id)
    await seed_run(org_id, proj_id, cost="0.003000")
    hdr = {"Authorization": f"Bearer {token}"}

    everything = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/usage", headers=hdr
    )
    assert everything.json()["total_calls"] == 2

    filtered = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/usage",
        params={"integration_id": integration_id},
        headers=hdr,
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["total_calls"] == 1
    assert Decimal(str(body["cost_usd"])) == Decimal("0.002000")
