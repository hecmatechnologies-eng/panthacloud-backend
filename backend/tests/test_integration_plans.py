import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models.membership import RoleEnum


@pytest.fixture
def make_git_repo():
    created_dirs = []

    def _create(fixture_name: str) -> Path:
        src = Path(__file__).parent / "fixtures" / "repositories" / fixture_name
        dest = Path(tempfile.mkdtemp(prefix="fussion_test_plan_git_"))
        created_dirs.append(dest)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "PlanTester"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial plan commit"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(dest), check=True, capture_output=True)
        return dest

    yield _create

    for d in created_dirs:
        def on_rm_error(func, path, exc_info):
            try:
                os.chmod(path, 0o777)
                func(path)
            except (OSError, PermissionError):
                pass
        shutil.rmtree(d, onerror=on_rm_error)


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
    user_id = data["user"]["id"]

    orgs_resp = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_resp.json()[0]["id"]
    return token, user_id, org_id


async def create_project(client: AsyncClient, token: str, org_id: str, name: str, slug: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": slug},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_integration(
    client: AsyncClient,
    token: str,
    org_id: str,
    proj_id: str,
    name: str,
) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "provider": "github",
            "configuration": {"repo": f"fussion-org/{name.lower()}"},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_repository(
    client: AsyncClient,
    token: str,
    org_id: str,
    proj_id: str,
    integ_id: str,
    name: str,
    url: str,
) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": name,
            "full_name": f"test-org/{name}",
            "external_id": f"gh-{name}",
            "default_branch": "main",
            "url": url,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def acquire_snapshot(
    client: AsyncClient,
    token: str,
    org_id: str,
    proj_id: str,
    repo_id: str,
) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers={"Authorization": f"Bearer {token}"},
        json={"branch": "main"},
    )
    assert resp.status_code == 201
    return resp.json()


async def run_discovery(
    client: AsyncClient,
    token: str,
    org_id: str,
    proj_id: str,
    repo_id: str,
    snapshot_id: str,
) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_integration_plan_lifecycle_and_security(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("integrations-demo")
    token, _, org_id = await register_user(client, "plan_owner@example.com", "Plan Owner")
    proj_id = await create_project(client, token, org_id, "Plan Proj", "plan-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Plan Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "integrations-demo", str(git_dir))

    # Snapshot & Discovery
    snap_data = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snapshot_id)

    # Generate integration plan
    plan_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert plan_resp.status_code == 201
    plan = plan_resp.json()

    assert plan["snapshot_id"] == snapshot_id
    assert plan["project_id"] == proj_id
    assert plan["status"] in ["READY", "REVIEW_REQUIRED"]

    # 1. Verify detected candidates
    candidates = plan["candidates"]
    candidate_names = {c["name"] for c in candidates}
    assert "PostgreSQL" in candidate_names
    assert "Redis" in candidate_names
    assert "Stripe" in candidate_names
    assert "Amazon S3" in candidate_names

    # Check candidate structure and confidence
    pg_cand = next(c for c in candidates if c["name"] == "PostgreSQL")
    assert pg_cand["type"] == "DATABASE"
    assert pg_cand["source"] == "DETECTED"
    assert pg_cand["confidence"] == "HIGH"
    assert len(pg_cand["evidence"]) >= 1

    # 2. Security invariant: Required credentials MUST NEVER expose secret values
    creds = plan["required_credentials"]
    assert len(creds) >= 3
    cred_names = {c["name"] for c in creds}
    assert "DATABASE_URL" in cred_names
    assert "REDIS_URL" in cred_names
    assert "STRIPE_SECRET_KEY" in cred_names

    # Assert no secret values are returned anywhere in credential definitions
    for c in creds:
        assert c["sensitive"] is True
        # Verify there is no 'value' field exposed
        assert "value" not in c
        # Ensure description does not leak test values from .env.example
        assert "sk_test" not in str(c.get("description", ""))

    # 3. Retrieve plan by ID
    plan_id = plan["id"]
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == plan_id

    # 4. List plans
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_integration_plan_with_contract_discrepancy(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("inconsistent-contract-demo")
    token, _, org_id = await register_user(client, "plan_discrepancy@example.com", "Plan Discrepancy")
    proj_id = await create_project(client, token, org_id, "Discrepancy Proj", "disc-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Disc Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "inconsistent-demo", str(git_dir))

    # Snapshot, Discovery, and Contract Normalization
    snap_data = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snapshot_id)

    contract_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert contract_resp.status_code == 201
    contract_id = contract_resp.json()["id"]

    # Generate plan linked to contract
    plan_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={"contract_id": contract_id},
    )
    assert plan_resp.status_code == 201
    plan = plan_resp.json()

    # Plan should be in REVIEW_REQUIRED status due to high impact questions
    assert plan["status"] == "REVIEW_REQUIRED"
    assert plan["contract_id"] == contract_id

    # Verify unresolved questions include contract discrepancy items
    questions = plan["unresolved_questions"]
    q_ids = {q["id"] for q in questions}
    assert "Q-CONTRACT-UNIMPLEMENTED-01" in q_ids
    assert "Q-CONTRACT-CONFLICT-01" in q_ids


@pytest.mark.asyncio
async def test_integration_plan_rbac_viewer(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("integrations-demo")
    owner_token, _, org_id = await register_user(client, "owner_p@example.com", "Owner P")
    proj_id = await create_project(client, owner_token, org_id, "RBAC Plan Proj", "rbac-plan-proj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "RBAC Plan Integ")
    repo_id = await create_repository(client, owner_token, org_id, proj_id, integ_id, "rbac-plan-repo", str(git_dir))

    snap_data = await acquire_snapshot(client, owner_token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]
    await run_discovery(client, owner_token, org_id, proj_id, repo_id, snapshot_id)

    # Register VIEWER
    viewer_token, _, _ = await register_user(client, "viewer_p@example.com", "Viewer P")
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "viewer_p@example.com", "role": RoleEnum.VIEWER.value},
    )
    assert invite_resp.status_code == 201

    # VIEWER cannot create plan -> 403 Forbidden
    forbid_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={},
    )
    assert forbid_resp.status_code == 403

    # OWNER creates plan
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={},
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["id"]

    # VIEWER can view plan -> 200 OK
    view_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans/{plan_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert view_resp.status_code == 200
    assert view_resp.json()["id"] == plan_id


@pytest.mark.asyncio
async def test_integration_plan_prerequisite_no_discovery(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("integrations-demo")
    token, _, org_id = await register_user(client, "nodisc_p@example.com", "No Disc P")
    proj_id = await create_project(client, token, org_id, "No Disc Proj P", "no-disc-proj-p")
    integ_id = await create_integration(client, token, org_id, proj_id, "No Disc Integ P")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "no-disc-repo-p", str(git_dir))

    # Acquire snapshot but do NOT run discovery
    snap_data = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 400
    assert "No completed discovery run found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_integration_plan_tenant_isolation_404(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("integrations-demo")
    token_a, _, org_a = await register_user(client, "plan_iso_a@example.com", "Iso A")
    proj_a = await create_project(client, token_a, org_a, "Iso Proj A", "iso-proj-a")
    integ_a = await create_integration(client, token_a, org_a, proj_a, "Iso Integ A")
    repo_a = await create_repository(client, token_a, org_a, proj_a, integ_a, "iso-repo-a", str(git_dir))

    snap_a = await acquire_snapshot(client, token_a, org_a, proj_a, repo_a)
    await run_discovery(client, token_a, org_a, proj_a, repo_a, snap_a["id"])

    plan_a = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a['id']}/integration-plans",
        headers={"Authorization": f"Bearer {token_a}"},
        json={},
    )
    plan_id = plan_a.json()["id"]

    # User B tries to view Plan A -> 404 anti-enumeration
    token_b, _, org_b = await register_user(client, "plan_iso_b@example.com", "Iso B")
    await create_project(client, token_b, org_b, "Iso Proj B", "iso-proj-b")

    leak_resp = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a['id']}/integration-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert leak_resp.status_code == 404
