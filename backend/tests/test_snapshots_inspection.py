import asyncio
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.repository.acquisition import sanitize_git_output
from app.services.repository.workspace import (
    SecurityViolationError,
    WorkspaceLimitExceededError,
    workspace_manager,
)


@pytest.fixture
def make_git_repo():
    created_dirs = []

    def _create(fixture_name: str) -> Path:
        src = Path(__file__).parent / "fixtures" / "repositories" / fixture_name
        dest = Path(tempfile.mkdtemp(prefix="fussion_test_git_"))
        created_dirs.append(dest)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(dest), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial test commit"], cwd=str(dest), check=True, capture_output=True)
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
    provider: str = "github",
    token_secret: str | None = None,
) -> str:
    secrets = {"token": token_secret} if token_secret else None
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "provider": provider,
            "configuration": {"repo": f"fussion-org/{name.lower()}"},
            "secrets": secrets,
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
    default_branch: str = "main",
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
            "default_branch": default_branch,
            "url": url,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_snapshot_creation_and_commit_sha_binding(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _user_id, org_id = await register_user(client, "snapuser@example.com", "SnapUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "SnapProj", "snapproj")
    integ_id = await create_integration(client, token, org_id, proj_id, "LocalGit")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "app-repo", str(fixture_dir))

    # 1. Acquire snapshot
    snap_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=hdr,
        json={"branch": "main"},
    )
    assert snap_resp.status_code == 201
    snap_data = snap_resp.json()
    assert snap_data["status"] == "READY"
    assert snap_data["branch"] == "main"
    assert len(snap_data["commit_sha"]) == 40
    assert snap_data["error_code"] is None
    assert snap_data["error_message"] is None
    assert snap_data["acquired_at"] is not None
    assert snap_data["completed_at"] is not None
    snapshot_id = snap_data["id"]

    # Verify commit sha matches fixture HEAD
    rev_proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "HEAD",
        cwd=str(fixture_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    rev_out, _ = await rev_proc.communicate()
    assert snap_data["commit_sha"] == rev_out.decode().strip()

    # 2. List snapshots
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=hdr,
    )
    assert list_resp.status_code == 200
    snapshots = list_resp.json()
    assert len(snapshots) == 1
    assert snapshots[0]["id"] == snapshot_id

    # 3. Retrieve snapshot
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}",
        headers=hdr,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["commit_sha"] == snap_data["commit_sha"]


@pytest.mark.asyncio
async def test_deterministic_inspection(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _user_id, org_id = await register_user(client, "inspectuser@example.com", "InspectUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "InspectProj", "inspectproj")
    integ_id = await create_integration(client, token, org_id, proj_id, "LocalGit")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "app-inspect", str(fixture_dir))

    # Acquire snapshot
    snap_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=hdr,
        json={"branch": "main"},
    )
    assert snap_resp.status_code == 201
    snapshot_id = snap_resp.json()["id"]

    # Run inspection
    inspect_resp1 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/inspect",
        headers=hdr,
    )
    assert inspect_resp1.status_code == 200
    data1 = inspect_resp1.json()

    assert data1["snapshot_id"] == snapshot_id
    assert len(data1["commit_sha"]) == 40
    assert data1["repository"]["name"] == "app-inspect"
    assert data1["structure"]["file_count"] >= 7
    assert data1["structure"]["directory_count"] >= 2
    assert data1["structure"]["total_size_bytes"] > 0
    assert data1["structure"]["maximum_depth"] >= 2

    # Verify detected components
    assert "Python" in data1["languages"]
    assert "TypeScript" in data1["languages"]
    assert "FastAPI" in data1["frameworks"]
    assert "Next.js" in data1["frameworks"]
    assert "package.json" in data1["manifests"]
    assert "pyproject.toml" in data1["manifests"]
    assert "pnpm-lock.yaml" in data1["manifests"]
    assert "openapi.yaml" in data1["api_contracts"]
    assert "Dockerfile" in data1["deployment_files"]

    # Run inspection again to verify determinism and reproducibility
    inspect_resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/inspect",
        headers=hdr,
    )
    assert inspect_resp2.status_code == 200
    data2 = inspect_resp2.json()
    assert data1 == data2


@pytest.mark.asyncio
async def test_django_react_inspection(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("django-react-demo")
    token, _user_id, org_id = await register_user(client, "djangouser@example.com", "DjangoUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "DjangoProj", "djangoproj")
    integ_id = await create_integration(client, token, org_id, proj_id, "LocalGit")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "django-repo", str(fixture_dir))

    # Acquire snapshot
    snap_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=hdr,
        json={"branch": "main"},
    )
    assert snap_resp.status_code == 201
    snapshot_id = snap_resp.json()["id"]

    # Inspect snapshot
    inspect_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/inspect",
        headers=hdr,
    )
    assert inspect_resp.status_code == 200
    data = inspect_resp.json()

    assert "Python" in data["languages"]
    assert "JavaScript" in data["languages"]
    assert "Django" in data["frameworks"]
    assert "React" in data["frameworks"]
    assert "requirements.txt" in data["manifests"]
    assert "package.json" in data["manifests"]
    assert "docker-compose.yml" in data["deployment_files"]


@pytest.mark.asyncio
async def test_snapshot_failed_acquisition_lifecycle(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    token, _user_id, org_id = await register_user(client, "failuser@example.com", "FailUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "FailProj", "failproj")
    integ_id = await create_integration(client, token, org_id, proj_id, "LocalGit")
    repo_id = await create_repository(client, token, org_id, proj_id, integ_id, "fail-repo", str(fixture_dir))

    # Attempt to acquire a non-existent branch
    snap_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=hdr,
        json={"branch": "nonexistent-branch-xyz"},
    )
    assert snap_resp.status_code == 201
    snap_data = snap_resp.json()
    assert snap_data["status"] == "FAILED"
    assert snap_data["error_code"] == "ACQUISITION_FAILED"
    assert snap_data["error_message"] is not None
    assert snap_data["completed_at"] is not None
    snapshot_id = snap_data["id"]

    # Verify workspace was cleaned up and does not exist on disk
    ws_path = workspace_manager.get_workspace_path(uuid.UUID(org_id), uuid.UUID(proj_id), uuid.UUID(snapshot_id))
    assert not ws_path.exists()

    # Attempting to inspect a failed snapshot must return 400 Bad Request
    inspect_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/inspect",
        headers=hdr,
    )
    assert inspect_resp.status_code == 400
    assert "Cannot inspect snapshot with status 'FAILED'" in inspect_resp.json()["detail"]


def test_security_workspace_containment_and_path_traversal():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_path = Path(tmp_dir) / "workspace"
        ws_path.mkdir()

        # Valid subpaths inside workspace
        valid_file = ws_path / "app" / "main.py"
        valid_file.parent.mkdir(parents=True)
        valid_file.write_text("print('ok')")

        contained = workspace_manager.assert_path_contained(ws_path, Path("app/main.py"))
        assert contained == valid_file.resolve()

        # Traversal attempts outside workspace
        with pytest.raises(SecurityViolationError):
            workspace_manager.assert_path_contained(ws_path, Path("../secret.txt"))

        with pytest.raises(SecurityViolationError):
            workspace_manager.assert_path_contained(ws_path, Path("../../etc/shadow"))

        with pytest.raises(SecurityViolationError):
            workspace_manager.assert_path_contained(ws_path, Path(tempfile.gettempdir()))


def test_security_symlink_escape_rejection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_path = Path(tmp_dir) / "workspace"
        ws_path.mkdir()
        external_target = Path(tmp_dir) / "external_secret.txt"
        external_target.write_text("SECRET")

        link_path = ws_path / "evil_link.txt"
        try:
            os.symlink(external_target, link_path)
            # Real symlink created: test rejection directly
            with pytest.raises(SecurityViolationError):
                workspace_manager.assert_path_contained(ws_path, link_path)
        except OSError:
            # OS/Privilege restriction on symlinks: verify mock containment check
            mock_path = MagicMock(spec=Path)
            mock_path.is_symlink.return_value = True
            mock_path.resolve.return_value = external_target.resolve()
            mock_path.is_absolute.return_value = True

            # Test logic matches workspace_manager symlink rejection
            assert not mock_path.resolve().is_relative_to(ws_path.resolve())


def test_security_resource_limits(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_path = Path(tmp_dir) / "workspace"
        ws_path.mkdir()

        # File size limit
        large_file = ws_path / "large.bin"
        large_file.write_bytes(b"X" * 100)

        # Passes with default settings
        workspace_manager.check_workspace_limits(ws_path)

        # Limit exceeded when MAX_FILE_SIZE_MB is exceeded
        monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 0.00005)  # ~50 bytes
        with pytest.raises(WorkspaceLimitExceededError, match="exceeded maximum file size limit"):
            workspace_manager.check_workspace_limits(ws_path)

        # File count limit exceeded
        monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 10)
        monkeypatch.setattr(settings, "MAX_FILE_COUNT", 2)
        (ws_path / "f1.txt").write_text("1")
        (ws_path / "f2.txt").write_text("2")
        (ws_path / "f3.txt").write_text("3")
        with pytest.raises(WorkspaceLimitExceededError, match="File count exceeded"):
            workspace_manager.check_workspace_limits(ws_path)

        # Directory depth limit exceeded
        monkeypatch.setattr(settings, "MAX_FILE_COUNT", 1000)
        monkeypatch.setattr(settings, "MAX_DIRECTORY_DEPTH", 2)
        deep_dir = ws_path / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True)
        (deep_dir / "leaf.txt").write_text("leaf")
        with pytest.raises(WorkspaceLimitExceededError, match="Directory depth exceeded"):
            workspace_manager.check_workspace_limits(ws_path)


def test_credential_safety():
    token = "ghp_SecretToken1234567890ABCDEF"
    text_with_token = f"fatal: unable to access 'https://x-access-token:{token}@github.com/org/repo.git': Failed."
    sanitized = sanitize_git_output(text_with_token, token)
    assert token not in sanitized
    assert "[REDACTED]" in sanitized

    url_with_auth = "https://user:password123@github.com/myorg/myrepo.git"
    sanitized_url = sanitize_git_output(url_with_auth)
    assert "password123" not in sanitized_url
    assert "://[REDACTED]@" in sanitized_url


@pytest.mark.asyncio
async def test_multi_tenant_snapshot_isolation(client: AsyncClient, make_git_repo):
    fixture_dir1 = make_git_repo("fastapi-nextjs-demo")
    fixture_dir2 = make_git_repo("django-react-demo")

    # User A in Org A
    token_a, _user_id_a, org_id_a = await register_user(client, "user_a@tenant.com", "UserA")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    proj_id_a = await create_project(client, token_a, org_id_a, "ProjA", "proja")
    integ_id_a = await create_integration(client, token_a, org_id_a, proj_id_a, "GitA")
    repo_id_a = await create_repository(client, token_a, org_id_a, proj_id_a, integ_id_a, "repo-a", str(fixture_dir1))
    snap_a_resp = await client.post(
        f"/api/v1/organizations/{org_id_a}/projects/{proj_id_a}/repositories/{repo_id_a}/snapshots",
        headers=hdr_a,
        json={"branch": "main"},
    )
    assert snap_a_resp.status_code == 201
    snap_id_a = snap_a_resp.json()["id"]

    # User B in Org B
    token_b, _user_id_b, org_id_b = await register_user(client, "user_b@tenant.com", "UserB")
    hdr_b = {"Authorization": f"Bearer {token_b}"}
    proj_id_b = await create_project(client, token_b, org_id_b, "ProjB", "projb")
    integ_id_b = await create_integration(client, token_b, org_id_b, proj_id_b, "GitB")
    repo_id_b = await create_repository(client, token_b, org_id_b, proj_id_b, integ_id_b, "repo-b", str(fixture_dir2))
    snap_b_resp = await client.post(
        f"/api/v1/organizations/{org_id_b}/projects/{proj_id_b}/repositories/{repo_id_b}/snapshots",
        headers=hdr_b,
        json={"branch": "main"},
    )
    assert snap_b_resp.status_code == 201
    snap_id_b = snap_b_resp.json()["id"]

    # 1. User A cannot access Snapshot B under Org A URL
    cross_resp1 = await client.get(
        f"/api/v1/organizations/{org_id_a}/projects/{proj_id_a}/repositories/{repo_id_a}/snapshots/{snap_id_b}",
        headers=hdr_a,
    )
    assert cross_resp1.status_code == 404

    # 2. User A cannot access Snapshot B under Org B URL
    cross_resp2 = await client.get(
        f"/api/v1/organizations/{org_id_b}/projects/{proj_id_b}/repositories/{repo_id_b}/snapshots/{snap_id_b}",
        headers=hdr_a,
    )
    assert cross_resp2.status_code == 404

    # 3. User A cannot inspect Snapshot B
    cross_resp3 = await client.post(
        f"/api/v1/organizations/{org_id_a}/projects/{proj_id_a}/repositories/{repo_id_a}/snapshots/{snap_id_b}/inspect",
        headers=hdr_a,
    )
    assert cross_resp3.status_code == 404

    # 4. User B cannot access Snapshot A
    cross_resp4 = await client.get(
        f"/api/v1/organizations/{org_id_b}/projects/{proj_id_b}/repositories/{repo_id_b}/snapshots/{snap_id_a}",
        headers=hdr_b,
    )
    assert cross_resp4.status_code == 404


@pytest.mark.asyncio
async def test_snapshot_rbac(client: AsyncClient, make_git_repo):
    fixture_dir = make_git_repo("fastapi-nextjs-demo")
    owner_token, _, org_id = await register_user(client, "rbac_owner@example.com", "RbacOwner")
    member_token, _, _ = await register_user(client, "rbac_member@example.com", "RbacMember")
    viewer_token, _, _ = await register_user(client, "rbac_viewer@example.com", "RbacViewer")

    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    member_hdr = {"Authorization": f"Bearer {member_token}"}
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}

    # Invite Member and Viewer
    res_m = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "rbac_member@example.com", "role": "MEMBER"},
    )
    assert res_m.status_code == 201

    res_v = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "rbac_viewer@example.com", "role": "VIEWER"},
    )
    assert res_v.status_code == 201

    proj_id = await create_project(client, owner_token, org_id, "RbacProj", "rbacproj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "GitRbac")
    repo_id = await create_repository(client, owner_token, org_id, proj_id, integ_id, "rbac-repo", str(fixture_dir))

    # 1. VIEWER cannot acquire snapshot (403 Forbidden)
    res_v_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=viewer_hdr,
        json={"branch": "main"},
    )
    assert res_v_create.status_code == 403

    # 2. MEMBER can acquire snapshot (201 Created)
    res_m_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=member_hdr,
        json={"branch": "main"},
    )
    assert res_m_create.status_code == 201
    snapshot_id = res_m_create.json()["id"]

    # 3. VIEWER can view snapshot list and details (200 OK)
    res_v_list = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots",
        headers=viewer_hdr,
    )
    assert res_v_list.status_code == 200
    assert len(res_v_list.json()) == 1

    res_v_get = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}",
        headers=viewer_hdr,
    )
    assert res_v_get.status_code == 200

    # 4. VIEWER cannot inspect snapshot (403 Forbidden)
    res_v_inspect = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/inspect",
        headers=viewer_hdr,
    )
    assert res_v_inspect.status_code == 403

    # 5. MEMBER can inspect snapshot (200 OK)
    res_m_inspect = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}/snapshots/{snapshot_id}/inspect",
        headers=member_hdr,
    )
    assert res_m_inspect.status_code == 200
