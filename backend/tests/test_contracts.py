import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models.membership import RoleEnum
from app.services.repository.contract import canonicalize_path, resolve_local_refs


@pytest.fixture
def make_git_repo():
    created_dirs = []

    def _create(fixture_name: str) -> Path:
        src = Path(__file__).parent / "fixtures" / "repositories" / fixture_name
        dest = Path(tempfile.mkdtemp(prefix="fussion_test_contract_git_"))
        created_dirs.append(dest)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "ContractTester"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial contract commit"], cwd=str(dest), check=True, capture_output=True)
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


# Unit tests for core algorithms
def test_canonicalize_path_rules():
    assert canonicalize_path("/users/:userId/posts/:postId") == "/users/{userId}/posts/{postId}"
    assert canonicalize_path("users/<int:user_id>/") == "/users/{user_id}"
    assert canonicalize_path("/api/v1/items/<item_id>") == "/api/v1/items/{item_id}"
    assert canonicalize_path("/") == "/"
    assert canonicalize_path("") == "/"
    assert canonicalize_path("/items/") == "/items"


def test_resolve_local_and_remote_refs():
    doc = {
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
                "Recursive": {
                    "type": "object",
                    "properties": {"parent": {"$ref": "#/components/schemas/Recursive"}},
                },
            }
        }
    }

    # 1. Local resolution
    ref_node = {"$ref": "#/components/schemas/User"}
    resolved = resolve_local_refs(ref_node, doc)
    assert resolved == {
        "type": "object",
        "properties": {"id": {"type": "string"}},
    }

    # 2. Remote ref refusal (never network fetch)
    remote_node = {"$ref": "https://api.example.com/schemas/User.json"}
    refused = resolve_local_refs(remote_node, doc)
    assert refused == {
        "$ref": "https://api.example.com/schemas/User.json",
        "status": "UNRESOLVED_EXTERNAL_REFERENCE",
    }

    # 3. Circular ref safe termination
    rec_node = {"$ref": "#/components/schemas/Recursive"}
    rec_resolved = resolve_local_refs(rec_node, doc)
    assert rec_resolved["properties"]["parent"] == {
        "$ref": "#/components/schemas/Recursive",
        "status": "CIRCULAR_REFERENCE",
    }


# Integration tests
@pytest.mark.asyncio
async def test_contract_lifecycle_and_binding(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("fastapi-contract-demo")
    token, _, org_id = await register_user(client, "contract_owner@example.com", "Contract Owner")
    proj_id = await create_project(client, token, org_id, "Contract Proj", "contract-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "FastAPI Contract Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "fastapi-contract-demo", str(git_dir))

    # Acquire snapshot
    snap_data = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]
    assert snap_data["status"] == "READY"
    assert snap_data["commit_sha"] is not None

    # Run discovery
    disc_data = await run_discovery(client, token, org_id, proj_id, repo_id, snapshot_id)
    assert disc_data["status"] == "COMPLETED"

    # Trigger contract normalization
    norm_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert norm_resp.status_code == 201
    contract = norm_resp.json()

    assert contract["status"] == "COMPLETED"
    assert contract["title"] == "User Management API"
    assert contract["version"] == "1.0.0"
    assert "openapi" in contract["format"]
    assert len(contract["servers"]) >= 1
    assert contract["servers"][0]["url"] == "https://api.example.com/v1"

    # Verify authentication schemes
    auth_schemes = contract["authentication"]
    assert len(auth_schemes) == 2
    auth_names = [a["name"] for a in auth_schemes]
    assert "ApiKeyAuth" in auth_names
    assert "BearerAuth" in auth_names

    # Verify schemas
    schemas = contract["schemas"]
    assert "User" in schemas
    assert "UserCreate" in schemas
    assert schemas["User"]["type"] == "object"

    # Verify operations and reconciliation
    ops = contract["operations"]
    assert len(ops) >= 3
    paths = {op["path"] for op in ops}
    assert "/users" in paths
    assert "/users/{id}" in paths

    # Check operations request / response schema resolution
    users_post = next(op for op in ops if op["path"] == "/users" and op["method"] == "POST")
    assert users_post["authentication_required"] is True
    assert users_post["request_schema"]["type"] == "object"
    assert users_post["response_schema"]["type"] == "object"

    # Verify reconciliation summary
    recon = contract["reconciliation"]
    assert recon["matched_count"] >= 3
    assert recon["documented_only_count"] == 0

    # Retrieve contract by ID
    contract_id = contract["id"]
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts/{contract_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == contract_id

    # List contracts for snapshot
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_contract_prerequisite_not_ready(client: AsyncClient, make_git_repo):
    token, _, org_id = await register_user(client, "noready@example.com", "No Ready User")
    proj_id = await create_project(client, token, org_id, "No Ready Proj", "no-ready-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "No Ready Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "no-ready-repo", "https://github.com/fake/repo")

    # Snapshot is PENDING because acquisition fails or is mock
    fake_snap_id = str(uuid.uuid4())
    # Normalizing on non-existent or un-ready snapshot
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{fake_snap_id}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_contract_prerequisite_no_discovery_run(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("fastapi-contract-demo")
    token, _, org_id = await register_user(client, "nodisc@example.com", "No Disc User")
    proj_id = await create_project(client, token, org_id, "No Disc Proj", "no-disc-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "No Disc Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "no-disc-repo", str(git_dir))

    # Acquire snapshot (READY)
    snap_data = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]

    # Attempt contract normalization without running discovery first
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 400
    assert "No completed discovery run found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_route_reconciliation_4_buckets(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("inconsistent-contract-demo")
    token, _, org_id = await register_user(client, "recon_tester@example.com", "Recon Tester")
    proj_id = await create_project(client, token, org_id, "Recon Proj", "recon-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Recon Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "inconsistent-demo", str(git_dir))

    # Acquire & Discover
    snap_data = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]
    await run_discovery(client, token, org_id, proj_id, repo_id, snapshot_id)

    # Normalize contract
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 201
    contract = resp.json()

    recon = contract["reconciliation"]
    # Verify the 4 distinct categories:
    # 1. /users GET -> MATCHED
    # 2. /documented-only GET -> DOCUMENTED_ONLY
    # 3. /code-only GET -> IMPLEMENTED_ONLY
    # 4. /conflict-path -> CONFLICT (contract has GET, code implements POST)
    assert recon["matched_count"] == 1
    assert recon["documented_only_count"] == 1
    assert recon["implemented_only_count"] == 1
    assert recon["conflict_count"] == 1

    findings = recon["findings"]
    categories = {f["path"]: f["category"] for f in findings}
    assert categories["/users"] == "MATCHED"
    assert categories["/documented-only"] == "DOCUMENTED_ONLY"
    assert categories["/code-only"] == "IMPLEMENTED_ONLY"
    assert categories["/conflict-path"] == "CONFLICT"


@pytest.mark.asyncio
async def test_contract_rbac_viewer(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("fastapi-contract-demo")
    owner_token, _, org_id = await register_user(client, "owner_c@example.com", "Owner C")
    proj_id = await create_project(client, owner_token, org_id, "RBAC Proj", "rbac-proj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "RBAC Integ")
    repo_id = await create_repository(client, owner_token, org_id, proj_id, integ_id, "rbac-repo", str(git_dir))

    # Acquire snapshot & discover as OWNER
    snap_data = await acquire_snapshot(client, owner_token, org_id, proj_id, repo_id)
    snapshot_id = snap_data["id"]
    await run_discovery(client, owner_token, org_id, proj_id, repo_id, snapshot_id)

    # Register VIEWER user
    viewer_token, _, _ = await register_user(client, "viewer_c@example.com", "Viewer C")

    # Invite viewer to org with VIEWER role
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "viewer_c@example.com", "role": RoleEnum.VIEWER.value},
    )
    assert invite_resp.status_code == 201

    # VIEWER tries to trigger contract normalization -> 403 Forbidden
    forbid_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={},
    )
    assert forbid_resp.status_code == 403

    # OWNER creates contract
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={},
    )
    assert create_resp.status_code == 201
    contract_id = create_resp.json()["id"]

    # VIEWER CAN view the contract -> 200 OK
    view_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/contracts/{contract_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert view_resp.status_code == 200
    assert view_resp.json()["id"] == contract_id


@pytest.mark.asyncio
async def test_contract_tenant_isolation_404(client: AsyncClient, make_git_repo):
    git_dir = make_git_repo("fastapi-contract-demo")
    token_a, _, org_a = await register_user(client, "org_a_user@example.com", "Org A")
    proj_a = await create_project(client, token_a, org_a, "Proj A", "proj-a")
    integ_a = await create_integration(client, token_a, org_a, proj_a, "Integ A")
    repo_a = await create_repository(client, token_a, org_a, proj_a, integ_a, "repo-a", str(git_dir))

    snap_a = await acquire_snapshot(client, token_a, org_a, proj_a, repo_a)
    await run_discovery(client, token_a, org_a, proj_a, repo_a, snap_a["id"])

    norm_a = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a['id']}/contracts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={},
    )
    contract_id = norm_a.json()["id"]

    # Org B user attempts to access Org A's contract -> 404 anti-enumeration
    token_b, _, org_b = await register_user(client, "org_b_user@example.com", "Org B")
    await create_project(client, token_b, org_b, "Proj B", "proj-b")

    leak_resp = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a['id']}/contracts/{contract_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert leak_resp.status_code == 404
