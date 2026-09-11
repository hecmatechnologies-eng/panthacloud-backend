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
        dest = Path(tempfile.mkdtemp(prefix="fussion_test_disc_git_"))
        created_dirs.append(dest)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "DiscoveryTester"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial discovery commit"], cwd=str(dest), check=True, capture_output=True)
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


@pytest.mark.asyncio
async def test_discovery_lifecycle_and_commit_binding(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "disc_lifecycle@example.com", "DiscUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "DiscProj", "disc-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-1", str(fixture_dir))

    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)
    snapshot_id = snap["id"]
    commit_sha = snap["commit_sha"]

    # 1. Trigger discovery
    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    disc = disc_resp.json()
    assert disc["status"] == "COMPLETED"
    assert disc["snapshot_id"] == snapshot_id
    assert disc["started_at"] is not None
    assert disc["completed_at"] is not None
    assert disc["error_code"] is None
    discovery_id = disc["id"]

    metadata = disc["metadata"]
    assert metadata["snapshot_id"] == snapshot_id
    assert metadata["commit_sha"] == commit_sha
    assert metadata["repository"]["name"] == "repo-1"

    # 2. List discoveries
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries",
        headers=hdr,
    )
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert len(runs) >= 1
    assert runs[0]["id"] == discovery_id

    # 3. Get discovery by id
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries/{discovery_id}",
        headers=hdr,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == discovery_id


@pytest.mark.asyncio
async def test_discovery_framework_detection(client: AsyncClient, make_git_repo):
    # Test FastAPI + Next.js detection
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "fw_fastapi@example.com", "FwUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "FwProj", "fw-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-fastapi", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    disc = disc_resp.json()
    frameworks = {f["name"]: f for f in disc["metadata"]["frameworks"]}
    assert "FastAPI" in frameworks
    assert "Next.js" in frameworks
    assert len(frameworks["FastAPI"]["evidence"]) > 0

    # Test Django + React detection
    django_dir = make_git_repo("django-react-demo")
    repo_django = await create_repository(client, token, org_id, proj_id, integ_id, "repo-django", str(django_dir))
    snap_django = await acquire_snapshot(client, token, org_id, proj_id, repo_django)

    disc_django = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_django}/snapshots/{snap_django['id']}/discoveries",
        headers=hdr,
    )
    assert disc_django.status_code == 201
    fw_django = {f["name"]: f for f in disc_django.json()["metadata"]["frameworks"]}
    assert "Django" in fw_django
    assert "React" in fw_django


@pytest.mark.asyncio
async def test_discovery_entrypoints(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "entrypoints@example.com", "EpUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "EpProj", "ep-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-ep", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    entrypoints = disc_resp.json()["metadata"]["entrypoints"]
    ep_symbols = {e["symbol"]: e for e in entrypoints}

    # FastAPI app instance
    assert "app" in ep_symbols
    assert ep_symbols["app"]["framework"] == "FastAPI"
    assert ep_symbols["app"]["type"] == "web_application"

    # Next.js page
    assert "Page" in ep_symbols
    assert ep_symbols["Page"]["framework"] == "Next.js"


@pytest.mark.asyncio
async def test_discovery_api_contracts_valid_and_invalid(client: AsyncClient, make_git_repo):
    # 1. Valid contract test
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "contract_valid@example.com", "CvUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "CvProj", "cv-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-cv", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    contracts = disc_resp.json()["metadata"]["api_contracts"]
    assert len(contracts) >= 1
    openapi_contract = next(c for c in contracts if c["file"] == "openapi.yaml")
    assert openapi_contract["format"] == "OpenAPI"
    assert openapi_contract["status"] == "VALID"
    assert openapi_contract["title"] == "FastAPI Demo API"
    assert openapi_contract["version"] == "0.1.0"
    assert openapi_contract["paths_count"] == 1
    assert openapi_contract["operations_count"] == 1
    assert openapi_contract["routes"][0]["method"] == "GET"
    assert openapi_contract["routes"][0]["path"] == "/health"

    # 2. Invalid contract test - ensures resilient handling without terminating discovery
    invalid_dir = make_git_repo("invalid-contract-demo")
    repo_inv = await create_repository(client, token, org_id, proj_id, integ_id, "repo-inv", str(invalid_dir))
    snap_inv = await acquire_snapshot(client, token, org_id, proj_id, repo_inv)

    disc_inv = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_inv}/snapshots/{snap_inv['id']}/discoveries",
        headers=hdr,
    )
    assert disc_inv.status_code == 201
    inv_data = disc_inv.json()
    assert inv_data["status"] == "COMPLETED"  # Did NOT crash
    inv_contracts = inv_data["metadata"]["api_contracts"]
    assert len(inv_contracts) == 1
    assert inv_contracts[0]["status"] == "INVALID"
    assert "parser" in inv_contracts[0]["error_message"].lower() or "syntax" in inv_contracts[0]["error_message"].lower()


@pytest.mark.asyncio
async def test_discovery_static_routes(client: AsyncClient, make_git_repo):
    # FastAPI static route extraction
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "routes_test@example.com", "RtUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "RtProj", "rt-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-rt", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    routes = disc_resp.json()["metadata"]["routes"]
    route_paths = {(r["method"], r["path"], r["handler"]): r for r in routes}

    assert ("GET", "/health", "health_check") in route_paths
    assert ("POST", "/items", "create_item") in route_paths
    assert ("GET", "/items/{item_id}", "get_item") in route_paths

    # Express routes test
    express_dir = make_git_repo("express-demo")
    repo_exp = await create_repository(client, token, org_id, proj_id, integ_id, "repo-exp", str(express_dir))
    snap_exp = await acquire_snapshot(client, token, org_id, proj_id, repo_exp)

    disc_exp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_exp}/snapshots/{snap_exp['id']}/discoveries",
        headers=hdr,
    )
    assert disc_exp.status_code == 201
    exp_routes = disc_exp.json()["metadata"]["routes"]
    exp_paths = {(r["method"], r["path"]): r for r in exp_routes}
    assert ("GET", "/api/users") in exp_paths
    assert ("POST", "/api/users") in exp_paths


@pytest.mark.asyncio
async def test_discovery_declared_dependencies(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "deps_test@example.com", "DpUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "DpProj", "dp-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-dp", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    dependencies = disc_resp.json()["metadata"]["dependencies"]
    dep_names = {d["name"]: d for d in dependencies}

    assert "fastapi" in dep_names
    assert dep_names["fastapi"]["manifest_file"] == "pyproject.toml"
    assert dep_names["fastapi"]["version_spec"] == ">=0.115.0"
    assert dep_names["fastapi"]["is_dev"] is False

    assert "uvicorn" in dep_names
    assert dep_names["uvicorn"]["version_spec"] == ">=0.30.0"


@pytest.mark.asyncio
async def test_discovery_configurations_and_sensitive_masking(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "cfg_masking@example.com", "CfgUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "CfgProj", "cfg-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-cfg", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert disc_resp.status_code == 201
    data = disc_resp.json()
    configs = data["metadata"]["configurations"]
    env_cfg = next((c for c in configs if c["file"] == ".env"), None)

    assert env_cfg is not None
    assert env_cfg["category"] == "environment"
    assert env_cfg["sensitive"] is True

    # Critical Security Check: Ensure sensitive file content is NEVER in metadata or response
    raw_response_text = disc_resp.text
    assert "postgresql://secret:password" not in raw_response_text
    assert "supersecretkey123" not in raw_response_text


@pytest.mark.asyncio
async def test_discovery_determinism(client: AsyncClient, make_git_repo):
    """Running discovery multiple times on the same commit SHA produces identical results."""
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _uid, org_id = await register_user(client, "determinism@example.com", "DetUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "DetProj", "det-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "repo-det", str(fixture_dir))
    snap = await acquire_snapshot(client, token, org_id, proj_id, repo_id)

    # First run
    run1 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert run1.status_code == 201
    meta1 = run1.json()["metadata"]

    # Second run
    run2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snap['id']}/discoveries",
        headers=hdr,
    )
    assert run2.status_code == 201
    meta2 = run2.json()["metadata"]

    # Assert lists are strictly equal in content and order
    assert meta1["frameworks"] == meta2["frameworks"]
    assert meta1["entrypoints"] == meta2["entrypoints"]
    assert meta1["routes"] == meta2["routes"]
    assert meta1["api_contracts"] == meta2["api_contracts"]
    assert meta1["dependencies"] == meta2["dependencies"]
    assert meta1["modules"] == meta2["modules"]
    assert meta1["configurations"] == meta2["configurations"]
    assert meta1["deployment"] == meta2["deployment"]


@pytest.mark.asyncio
async def test_discovery_tenant_isolation_anti_enumeration(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    # Org A
    token_a, _uid_a, org_a = await register_user(client, "org_a_user@example.com", "UserA")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    proj_a = await create_project(client, token_a, org_a, "ProjA", "proj-a")
    integ_a = await create_integration(client, token_a, org_a, proj_a, "IntegA")
    repo_a = await create_repository(client, token_a, org_a, proj_a, integ_a, "repo-a", str(fixture_dir))
    snap_a = await acquire_snapshot(client, token_a, org_a, proj_a, repo_a)

    disc_resp = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}/snapshots/{snap_a['id']}/discoveries",
        headers=hdr_a,
    )
    assert disc_resp.status_code == 201
    disc_id_a = disc_resp.json()["id"]

    # Org B
    token_b, _uid_b, org_b = await register_user(client, "org_b_user@example.com", "UserB")
    hdr_b = {"Authorization": f"Bearer {token_b}"}
    proj_b = await create_project(client, token_b, org_b, "ProjB", "proj-b")

    # User B attempts to access User A's discovery run -> must return 404 (anti-enumeration)
    cross_get = await client.get(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/repositories/{repo_a}/snapshots/{snap_a['id']}/discoveries/{disc_id_a}",
        headers=hdr_b,
    )
    assert cross_get.status_code == 404

    cross_post = await client.post(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/repositories/{repo_a}/snapshots/{snap_a['id']}/discoveries",
        headers=hdr_b,
    )
    assert cross_post.status_code == 404


@pytest.mark.asyncio
async def test_discovery_rbac_permissions(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    owner_token, _owner_id, org_id = await register_user(client, "rbac_owner@example.com", "RbacOwner")
    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    proj_id = await create_project(client, owner_token, org_id, "RbacProj", "rbac-proj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "Integ")
    repo_id = await create_repository(client, owner_token, org_id, proj_id, integ_id, "repo-rbac", str(fixture_dir))
    snap = await acquire_snapshot(client, owner_token, org_id, proj_id, repo_id)
    snapshot_id = snap["id"]

    # Create VIEWER user
    viewer_token, _viewer_id, _v_org = await register_user(client, "rbac_viewer@example.com", "RbacViewer")
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}

    # Invite viewer to Org with VIEWER role
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "rbac_viewer@example.com", "role": RoleEnum.VIEWER.value},
    )
    assert invite_resp.status_code == 201

    # Viewer attempts to create discovery -> 403 Forbidden
    forbidden_post = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries",
        headers=viewer_hdr,
    )
    assert forbidden_post.status_code == 403

    # Owner creates discovery -> 201 Created
    owner_post = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries",
        headers=owner_hdr,
    )
    assert owner_post.status_code == 201
    disc_id = owner_post.json()["id"]

    # Viewer can read discovery -> 200 OK
    viewer_get = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/discoveries/{disc_id}",
        headers=viewer_hdr,
    )
    assert viewer_get.status_code == 200
    assert viewer_get.json()["id"] == disc_id
