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
        dest = Path(tempfile.mkdtemp(prefix="fussion_test_exec_git_"))
        created_dirs.append(dest)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "ExecTester"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial exec commit"], cwd=str(dest), check=True, capture_output=True)
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


async def create_integration(client: AsyncClient, token: str, org_id: str, proj_id: str, name: str) -> str:
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


async def create_repository(client: AsyncClient, token: str, org_id: str, proj_id: str, integ_id: str, name: str, url: str) -> str:
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


async def acquire_snapshot(client: AsyncClient, token: str, org_id: str, proj_id: str, repo_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers={"Authorization": f"Bearer {token}"},
        json={"branch": "main"},
    )
    assert resp.status_code == 201
    return resp.json()


async def run_discovery(client: AsyncClient, token: str, org_id: str, proj_id: str, repo_id: str, snapshot_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


async def run_integration_plan(client: AsyncClient, token: str, org_id: str, proj_id: str, repo_id: str, snapshot_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/integration-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.anyio
async def test_execution_plan_lifecycle(client: AsyncClient, make_git_repo):
    """Test full execution plan generation, listing, and retrieval."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "exec_life@example.com", "ExecLife")
    proj_id = await create_project(client, token, org_id, "Exec Project", "exec-project")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    # 1. Create execution plan
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    plan = resp.json()
    assert plan["snapshot_id"] == snap_id
    assert len(plan["steps"]) >= 3

    # 2. List execution plans
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    plans = list_resp.json()
    assert len(plans) >= 1

    # 3. Retrieve single execution plan
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans/{plan['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    single = get_resp.json()
    assert single["id"] == plan["id"]


@pytest.mark.anyio
async def test_execution_plan_step_ordering_and_dependencies(client: AsyncClient, make_git_repo):
    """Verify deterministic step IDs (step-1, step-2...) and explicit dependency chaining."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "order_tester@example.com", "OrderTester")
    proj_id = await create_project(client, token, org_id, "Order Proj", "order-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    plan = resp.json()
    steps = plan["steps"]

    # Verify deterministic step IDs
    for idx, s in enumerate(steps, start=1):
        assert s["id"] == f"step-{idx}"
        assert s["order"] == idx

    # Step 1 has no dependencies
    assert steps[0]["depends_on"] == []
    assert steps[0]["action"] == "validate_configuration_keys"

    # Step 2 depends on step-1
    assert steps[1]["depends_on"] == ["step-1"]
    assert steps[1]["action"] == "validate_adapter_prerequisites"

    # Subsequent steps depend on step-2
    for s in steps[2:]:
        assert "step-2" in s["depends_on"]


@pytest.mark.anyio
async def test_execution_plan_safety_classifications(client: AsyncClient, make_git_repo):
    """Verify safety classifications: CONFIGURATION, READ_ONLY, WRITE, EXTERNAL_NETWORK, CREDENTIAL_REQUIRED."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "safety_tester@example.com", "SafetyTester")
    proj_id = await create_project(client, token, org_id, "Safety Proj", "safety-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    steps = resp.json()["steps"]

    # Step 1: CONFIGURATION and READ_ONLY
    assert "CONFIGURATION" in steps[0]["safety_classifications"]
    assert "READ_ONLY" in steps[0]["safety_classifications"]

    # Step 2: READ_ONLY and EXTERNAL_NETWORK
    assert "READ_ONLY" in steps[1]["safety_classifications"]
    assert "EXTERNAL_NETWORK" in steps[1]["safety_classifications"]

    # Payment/Storage write steps
    payment_steps = [s for s in steps if "stripe" in s["action"].lower()]
    assert len(payment_steps) > 0
    for ps in payment_steps:
        assert "WRITE" in ps["safety_classifications"]
        assert "EXTERNAL_NETWORK" in ps["safety_classifications"]
        assert "CREDENTIAL_REQUIRED" in ps["safety_classifications"]


@pytest.mark.anyio
async def test_execution_plan_approval_and_blocked_boundaries(client: AsyncClient, make_git_repo):
    """Verify write/external steps require approval and all external steps are BLOCKED."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "approval_tester@example.com", "ApprovalTester")
    proj_id = await create_project(client, token, org_id, "Approval Proj", "approval-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    plan = resp.json()
    steps = plan["steps"]

    # Step 1 is READY (pure config validation)
    assert steps[0]["status"] == "READY"
    assert steps[0]["requires_approval"] is False

    # External steps are BLOCKED
    for s in steps[1:]:
        assert s["status"] == "BLOCKED"
        assert s["blocked_reason"] is not None
        assert "Phase 08" in s["blocked_reason"]

    # Financial / Mutation steps require approval
    approved_steps = [s for s in steps if s["requires_approval"]]
    assert len(approved_steps) > 0
    assert len(plan["approval_requirements"]) > 0


@pytest.mark.anyio
async def test_execution_plan_credential_references_without_values(client: AsyncClient, make_git_repo):
    """Verify inputs reference variable names only, with zero secret values."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "cred_ref@example.com", "CredRef")
    proj_id = await create_project(client, token, org_id, "CredRef Proj", "credref-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    plan = resp.json()

    for cred in plan["required_credentials"]:
        assert "key" in cred
        assert "value" not in cred
        assert "secret" not in cred
        assert cred["sensitive"] is True

    for s in plan["steps"]:
        for inp in s["inputs"]:
            # Inputs must be variable name strings
            assert isinstance(inp, str)
            assert not any(c in inp for c in ["password", "secret123", "token_val"])


@pytest.mark.anyio
async def test_execution_plan_tenant_isolation_anti_enumeration(client: AsyncClient, make_git_repo):
    """Verify cross-tenant access returns 404 to prevent resource enumeration."""
    git_dir = make_git_repo("payments-storage-demo")
    token_a, _, org_a = await register_user(client, "exec_user_a@example.com", "ExecUserA")
    token_b, _, _ = await register_user(client, "exec_user_b@example.com", "ExecUserB")

    proj_a = await create_project(client, token_a, org_a, "Project A", "project-a")
    integ_a = await create_integration(client, token_a, org_a, proj_a, "GitHub Int")
    repo_a = await create_repository(client, token_a, org_a, proj_a, integ_a, "repo-a", str(git_dir))

    snap_a = await acquire_snapshot(client, token_a, org_a, proj_a, repo_a)
    snap_a_id = snap_a["id"]
    await run_discovery(client, token_a, org_a, proj_a, repo_a, snap_a_id)
    await run_integration_plan(client, token_a, org_a, proj_a, repo_a, snap_a_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a_id}/execution-plans",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    plan_id = resp.json()["id"]

    # Cross-tenant list -> 404
    cross_list = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a_id}/execution-plans",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_list.status_code == 404

    # Cross-tenant get -> 404
    cross_get = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a_id}/execution-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_get.status_code == 404


@pytest.mark.anyio
async def test_execution_plan_rbac_permissions(client: AsyncClient, make_git_repo):
    """Verify VIEWER receives 403 on create, 200 on list and retrieve."""
    git_dir = make_git_repo("payments-storage-demo")
    owner_token, _, org_id = await register_user(client, "exec_owner@example.com", "ExecOwner")
    proj_id = await create_project(client, owner_token, org_id, "Exec Proj", "exec-proj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, owner_token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, owner_token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, owner_token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, owner_token, org_id, proj_id, repo_id, snap_id)

    # Add VIEWER user
    viewer_token, _viewer_id, _ = await register_user(client, "exec_viewer@example.com", "ExecViewer")
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "exec_viewer@example.com", "role": RoleEnum.VIEWER.value},
    )
    assert invite_resp.status_code == 201

    # VIEWER creates execution plan -> 403 Forbidden
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert create_resp.status_code == 403

    # OWNER creates execution plan -> 201 Created
    owner_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_create.status_code == 201
    plan_id = owner_create.json()["id"]

    # VIEWER lists execution plans -> 200 OK
    viewer_list = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert viewer_list.status_code == 200

    # VIEWER retrieves single execution plan -> 200 OK
    viewer_get = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/execution-plans/{plan_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert viewer_get.status_code == 200
