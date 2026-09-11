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
        dest = Path(tempfile.mkdtemp(prefix="fussion_test_adapter_git_"))
        created_dirs.append(dest)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "AdapterTester"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial adapter commit"], cwd=str(dest), check=True, capture_output=True)
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
async def test_adapter_planning_lifecycle(client: AsyncClient, make_git_repo):
    """Test full adapter generation, listing, and individual retrieval lifecycle."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "adapter_life@example.com", "AdapterLife")
    proj_id = await create_project(client, token, org_id, "Adapter Project", "adapter-project")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    # 1. Generate adapters
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 201:
        print("ERROR DETAIL:", resp.json())
    assert resp.status_code == 201
    adapters = resp.json()
    assert isinstance(adapters, list)
    assert len(adapters) > 0

    # 2. List adapters
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data) == len(adapters)

    # 3. Retrieve single adapter
    first_adapter = adapters[0]
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters/{first_adapter['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    single = get_resp.json()
    assert single["id"] == first_adapter["id"]
    assert single["adapter_type"] == first_adapter["adapter_type"]


@pytest.mark.anyio
async def test_adapter_classification_payments_storage(client: AsyncClient, make_git_repo):
    """Verify PostgreSQL (DATABASE), Redis (CACHE), Stripe (PAYMENT), AWS S3 (STORAGE) are correctly classified."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "classify@example.com", "ClassifyUser")
    proj_id = await create_project(client, token, org_id, "Classify Proj", "classify-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    adapters = resp.json()

    adapter_types = {a["adapter_type"] for a in adapters}
    providers = {a["provider"] for a in adapters if a["provider"]}

    assert "DATABASE" in adapter_types
    assert "CACHE" in adapter_types
    assert "PAYMENT" in adapter_types
    assert "STORAGE" in adapter_types

    assert "PostgreSQL" in providers
    assert "Redis" in providers
    assert "Stripe" in providers
    assert "Amazon S3" in providers

    # Verify operations inside Stripe Payment adapter
    stripe_adapter = next(a for a in adapters if a["provider"] == "Stripe")
    assert stripe_adapter["status"] == "PLANNED"
    assert any(op["requires_approval"] for op in stripe_adapter["operations"])


@pytest.mark.anyio
async def test_adapter_webhook_detection(client: AsyncClient, make_git_repo):
    """Verify webhook routes produce declarative WEBHOOK adapter."""
    git_dir = make_git_repo("webhook-demo")
    token, _, org_id = await register_user(client, "webhook_tester@example.com", "WebhookTester")
    proj_id = await create_project(client, token, org_id, "Webhook Proj", "webhook-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "webhook-demo", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    adapters = resp.json()

    webhook_adapters = [a for a in adapters if a["adapter_type"] == "WEBHOOK"]
    assert len(webhook_adapters) >= 1
    wh = webhook_adapters[0]
    assert wh["status"] == "PLANNED"
    assert any(op["operation_type"] == "RECEIVE" for op in wh["operations"])


@pytest.mark.anyio
async def test_adapter_unknown_classification(client: AsyncClient, make_git_repo):
    """Verify unclassified dependencies produce UNKNOWN adapter with REVIEW_REQUIRED."""
    git_dir = make_git_repo("adapter-unknown-demo")
    token, _, org_id = await register_user(client, "unknown_tester@example.com", "UnknownTester")
    proj_id = await create_project(client, token, org_id, "Unknown Proj", "unknown-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "unknown-demo", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    adapters = resp.json()

    unknown_adapters = [a for a in adapters if a["adapter_type"] == "UNKNOWN"]
    assert len(unknown_adapters) >= 1
    un = unknown_adapters[0]
    assert un["status"] == "REVIEW_REQUIRED"
    assert un["provider"] is None


@pytest.mark.anyio
async def test_adapter_credential_safety_zero_values(client: AsyncClient, make_git_repo):
    """Verify zero secret values are returned or persisted; only variable names and metadata."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "cred_safety@example.com", "CredSafety")
    proj_id = await create_project(client, token, org_id, "Cred Proj", "cred-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    adapters = resp.json()

    for adapter in adapters:
        for cred in adapter["required_credentials"]:
            assert "key" in cred
            assert "value" not in cred
            assert "secret" not in cred
            assert "token" not in cred
            assert cred.get("sensitive") is True


@pytest.mark.anyio
async def test_adapter_determinism(client: AsyncClient, make_git_repo):
    """Verify run-to-run determinism for identical snapshot inputs."""
    git_dir = make_git_repo("payments-storage-demo")
    token, _, org_id = await register_user(client, "determ_user@example.com", "DetermUser")
    proj_id = await create_project(client, token, org_id, "Determ Proj", "determ-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, token, org_id, proj_id, repo_id, snap_id)

    # Run 1
    resp1 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    data1 = resp1.json()

    # Run 2
    resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token}"},
    )
    data2 = resp2.json()

    assert len(data1) == len(data2)
    for a1, a2 in zip(data1, data2, strict=False):
        assert a1["name"] == a2["name"]
        assert a1["adapter_type"] == a2["adapter_type"]
        assert a1["status"] == a2["status"]
        assert len(a1["operations"]) == len(a2["operations"])


@pytest.mark.anyio
async def test_adapter_tenant_isolation_anti_enumeration(client: AsyncClient, make_git_repo):
    """Verify cross-tenant access returns 404 Not Found to prevent enumeration."""
    git_dir = make_git_repo("payments-storage-demo")
    token_a, _, org_a = await register_user(client, "org_a_user@example.com", "UserA")
    token_b, _, _ = await register_user(client, "org_b_user@example.com", "UserB")

    proj_a = await create_project(client, token_a, org_a, "Project A", "project-a")
    integ_a = await create_integration(client, token_a, org_a, proj_a, "GitHub Int")
    repo_a = await create_repository(client, token_a, org_a, proj_a, integ_a, "repo-a", str(git_dir))

    snap_a = await acquire_snapshot(client, token_a, org_a, proj_a, repo_a)
    snap_a_id = snap_a["id"]
    await run_discovery(client, token_a, org_a, proj_a, repo_a, snap_a_id)
    await run_integration_plan(client, token_a, org_a, proj_a, repo_a, snap_a_id)

    # Org A creates adapters
    resp = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    adapter_id = resp.json()[0]["id"]

    # Org B attempts to access Org A's adapters -> 404
    cross_list = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a_id}/integration-adapters",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_list.status_code == 404

    cross_get = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a_id}/integration-adapters/{adapter_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_get.status_code == 404


@pytest.mark.anyio
async def test_adapter_rbac_permissions(client: AsyncClient, make_git_repo):
    """Verify VIEWER receives 403 on create, but 200 on list and retrieve."""
    git_dir = make_git_repo("payments-storage-demo")
    owner_token, _, org_id = await register_user(client, "rbac_owner@example.com", "RBACOwner")
    proj_id = await create_project(client, owner_token, org_id, "RBAC Proj", "rbac-proj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "GitHub Int")
    repo_id = await create_repository(client, owner_token, org_id, proj_id, integ_id, "payments-storage", str(git_dir))

    snap = await acquire_snapshot(client, owner_token, org_id, proj_id, repo_id)
    snap_id = snap["id"]
    await run_discovery(client, owner_token, org_id, proj_id, repo_id, snap_id)
    await run_integration_plan(client, owner_token, org_id, proj_id, repo_id, snap_id)

    # Add VIEWER user
    viewer_token, _viewer_id, _ = await register_user(client, "rbac_viewer@example.com", "RBACViewer")
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "rbac_viewer@example.com", "role": RoleEnum.VIEWER.value},
    )
    assert invite_resp.status_code == 201

    # VIEWER attempts to create adapters -> 403 Forbidden
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert create_resp.status_code == 403

    # OWNER creates adapters
    owner_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_create.status_code == 201
    adapter_id = owner_create.json()[0]["id"]

    # VIEWER lists adapters -> 200 OK
    viewer_list = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert viewer_list.status_code == 200

    # VIEWER retrieves single adapter -> 200 OK
    viewer_get = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap_id}/integration-adapters/{adapter_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert viewer_get.status_code == 200
