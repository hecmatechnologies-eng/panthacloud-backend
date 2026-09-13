import base64
import json
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.secrets import secret_store
from app.models.audit_event import AuditEvent
from app.models.project import Project
from app.models.website_integration import (
    IntegrationRun,
    IntegrationRunStatus,
    WebsiteIntegration,
)
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.artifacts import (
    generate_artifacts,
    patch_html_index,
    patch_react_layout,
)
from app.services.integration.git_provider import GitProvider
from app.services.integration.github import (
    GitHubAPIError,
    GitHubProvider,
    GitHubUnavailableError,
    MockGitProvider,
    set_git_provider,
)
from app.services.integration.sandbox import LocalWorkspaceProvider, SandboxSecurityError
from app.services.integration.validation import StaticValidationError, StaticValidator

DISTINCTIVE_REPO = Path(__file__).parent / "fixtures" / "repositories" / "nextjs-distinctive-layout"


def read_fixture(rel_path: str) -> str:
    # Bytes, not read_text(): keep the on-disk line endings, as GitHub would return them.
    return (DISTINCTIVE_REPO / rel_path).read_bytes().decode("utf-8")


def load_distinctive_repo(mock_git: MockGitProvider, owner: str, repo: str) -> None:
    mock_git.add_repository(owner, repo)
    for file in DISTINCTIVE_REPO.rglob("*"):
        if file.is_file():
            rel_path = file.relative_to(DISTINCTIVE_REPO).as_posix()
            mock_git.add_file(owner, repo, rel_path, read_fixture(rel_path))


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


# ============================================================
# 1. INTEGRATION CRUD, SECRET ENCRYPTION & REDACTION
# ============================================================


@pytest.mark.asyncio
async def test_website_integration_crud_and_secrets(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "web_integ_owner@example.com", "WebOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Shop Proj", "shop-proj")

    # 1. Initially 404
    get_init = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
    )
    assert get_init.status_code == 404

    # 2. Create integration with GitHub token
    raw_token = "ghp_secret_access_token_1234567890abcdef"
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
            "default_branch": "main",
            "framework_skill_id": "nextjs-app-router",
            "website_root_dir": "/",
            "widget_target_path": "app/layout.tsx",
            "github_token": raw_token,
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["repository_owner"] == "fussion-org"
    assert data["repository_name"] == "storefront"
    assert data["framework_skill_id"] == "nextjs-app-router"
    assert data["has_credentials"] is True
    # Verify strict secret redaction
    assert "github_token" not in data
    assert "encrypted_secrets" not in data
    assert raw_token not in str(data)

    # 3. Read integration via GET
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == data["id"]
    assert get_resp.json()["has_credentials"] is True

    # 4. Verify alias /website-integration also works
    alias_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integration",
        headers=hdr,
    )
    assert alias_resp.status_code == 200
    assert alias_resp.json()["id"] == data["id"]

    # 5. Duplicate creation in same project is rejected
    dup_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
        },
    )
    assert dup_resp.status_code == 400

    # 6. Verify secret encryption in DB
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(WebsiteIntegration).where(WebsiteIntegration.id == uuid.UUID(data["id"]))
        integ_db = (await db.execute(stmt)).scalar_one()
        assert integ_db.encrypted_secrets is not None
        assert raw_token not in integ_db.encrypted_secrets
        decrypted = secret_store.decrypt(integ_db.encrypted_secrets)
        assert decrypted["github_token"] == raw_token

    # 7. Partial update without touching token preserves token
    patch_resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={"widget_target_path": "src/app/layout.tsx"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["widget_target_path"] == "src/app/layout.tsx"
    assert patch_resp.json()["has_credentials"] is True

    # 8. Delete integration
    del_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
    )
    assert del_resp.status_code == 204

    # 9. Verify gone
    get_after = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
    )
    assert get_after.status_code == 404


@pytest.mark.asyncio
async def test_website_integration_rejects_unknown_framework_skill(client: AsyncClient) -> None:
    """FR-082: an unknown skill id is refused at configuration time, not planned as an empty run."""
    token, _, org_id = await register_user(client, "web_integ_skill@example.com", "SkillOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Skill Proj", "skill-proj")

    unknown = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
            "framework_skill_id": "django-magic",
        },
    )
    assert unknown.status_code == 422

    too_long = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
            "framework_skill_id": "x" * 101,
        },
    )
    assert too_long.status_code == 422


# ============================================================
# 2. REPOSITORY VALIDATION & ERROR HANDLING
# ============================================================


@pytest.mark.asyncio
async def test_repository_validation_success_and_failure(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "val_owner@example.com", "ValOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Val Proj", "val-proj")

    # Connect to valid repository
    mock_git = MockGitProvider()
    set_git_provider(mock_git)

    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
            "framework_skill_id": "nextjs-app-router",
        },
    )

    # Initialize assistant for project
    await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/assistant",
        headers=hdr,
    )

    # Validate valid repository
    val_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/validate",
        headers=hdr,
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["status"] == "VALID"
    assert val_data["is_valid"] is True
    assert val_data["assistant_readiness"] is True
    assert len(val_data["issues"]) == 0

    # Test repository not found
    await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={"repository_name": "nonexistent-repo"},
    )
    val_fail = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/validate",
        headers=hdr,
    )
    assert val_fail.status_code == 200
    fail_data = val_fail.json()
    assert fail_data["status"] == "INVALID"
    assert fail_data["is_valid"] is False
    assert any("not found" in issue.lower() for issue in fail_data["issues"])


# ============================================================
# 3. MULTI-TENANT & CROSS-PROJECT ISOLATION
# ============================================================


@pytest.mark.asyncio
async def test_website_integration_multi_tenant_isolation(client: AsyncClient) -> None:
    token_a, _, org_a = await register_user(client, "iso_a@example.com", "IsoA")
    token_b, _, org_b = await register_user(client, "iso_b@example.com", "IsoB")

    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    proj_a = await create_project(client, token_a, org_a, "Proj A", "proj-a")
    proj_b = await create_project(client, token_b, org_b, "Proj B", "proj-b")

    # Create integration in Org A
    await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/website-integrations",
        headers=hdr_a,
        json={"repository_owner": "org-a", "repository_name": "repo-a"},
    )

    # 1. User A in Org A -> Allowed (200)
    res_a = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/website-integrations",
        headers=hdr_a,
    )
    assert res_a.status_code == 200

    # 2. User B accessing Org A's integration -> 404 (Anti-enumeration)
    res_b_to_a = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/website-integrations",
        headers=hdr_b,
    )
    assert res_b_to_a.status_code == 404

    # 3. User A accessing Org B's project -> 404
    res_a_to_b = await client.get(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/website-integrations",
        headers=hdr_a,
    )
    assert res_a_to_b.status_code == 404


# ============================================================
# 4. RBAC MATRIX
# ============================================================


@pytest.mark.asyncio
async def test_website_integration_rbac(client: AsyncClient) -> None:
    owner_token, _, org_id = await register_user(client, "wb_rbac_owner@example.com", "RbacOwner")
    admin_token, _, _ = await register_user(client, "wb_rbac_admin@example.com", "RbacAdmin")
    member_token, _, _ = await register_user(client, "wb_rbac_member@example.com", "RbacMember")
    viewer_token, _, _ = await register_user(client, "wb_rbac_viewer@example.com", "RbacViewer")

    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    admin_hdr = {"Authorization": f"Bearer {admin_token}"}
    member_hdr = {"Authorization": f"Bearer {member_token}"}
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}

    # Add roles to org
    for email, role in [
        ("wb_rbac_admin@example.com", "ADMIN"),
        ("wb_rbac_member@example.com", "MEMBER"),
        ("wb_rbac_viewer@example.com", "VIEWER"),
    ]:
        await client.post(
            f"/api/v1/organizations/{org_id}/members",
            headers=owner_hdr,
            json={"email": email, "role": role},
        )

    proj_id = await create_project(client, owner_token, org_id, "RBAC Website", "rbac-website")

    # 1. VIEWER cannot create integration -> 403
    v_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=viewer_hdr,
        json={"repository_owner": "org", "repository_name": "repo"},
    )
    assert v_create.status_code == 403

    # 2. MEMBER CAN create integration -> 201
    m_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=member_hdr,
        json={"repository_owner": "org", "repository_name": "repo"},
    )
    assert m_create.status_code == 201

    # 3. VIEWER CAN view integration -> 200
    v_view = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=viewer_hdr,
    )
    assert v_view.status_code == 200

    # 4. VIEWER cannot update integration -> 403
    v_patch = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=viewer_hdr,
        json={"default_branch": "release"},
    )
    assert v_patch.status_code == 403

    # 5. VIEWER cannot validate -> 403
    v_val = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/validate",
        headers=viewer_hdr,
    )
    assert v_val.status_code == 403

    # 6. VIEWER cannot execute runs -> 403
    v_run = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs",
        headers=viewer_hdr,
    )
    assert v_run.status_code == 403

    # 7. VIEWER cannot delete -> 403
    v_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=viewer_hdr,
    )
    assert v_del.status_code == 403

    # 8. MEMBER CAN update integration -> 200
    m_patch = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=member_hdr,
        json={"default_branch": "release"},
    )
    assert m_patch.status_code == 200

    # 9. ADMIN CAN delete integration -> 204
    a_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=admin_hdr,
    )
    assert a_del.status_code == 204


# ============================================================
# 5. SANDBOX SECURITY & TRAVERSAL REJECTION
# ============================================================


def test_sandbox_path_traversal_rejection() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sbx = LocalWorkspaceProvider(base_dir=tmpdir)
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        run_id = uuid.uuid4()
        sandbox_path, _ = sbx.allocate(org_id, proj_id, run_id)

        # 1. Reject parent directory escape (../)
        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "../secret.txt")

        # 2. Reject nested parent directory escape (../../etc/passwd)
        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "../../etc/passwd")

        # 3. Reject absolute POSIX path
        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "/etc/passwd")

        # 4. Reject Windows absolute path
        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "C:\\Windows\\System32\\cmd.exe")

        # 5. Reject Windows device path (NUL, CON)
        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "CON")

        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "NUL")

        # 6. Reject null byte in path
        with pytest.raises(SandboxSecurityError):
            sbx.assert_path_contained(sandbox_path, "valid/path\0escape.txt")

        # 7. Valid path resolves inside sandbox
        valid_path = sbx.write_file(sandbox_path, "components/widget.tsx", "content")
        assert valid_path.exists()
        assert sbx.read_file(sandbox_path, "components/widget.tsx") == "content"


def test_sandbox_isolation_between_runs() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sbx = LocalWorkspaceProvider(base_dir=tmpdir)
        org_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        run1 = uuid.uuid4()
        run2 = uuid.uuid4()

        p1, ref1 = sbx.allocate(org_id, proj_id, run1)
        p2, ref2 = sbx.allocate(org_id, proj_id, run2)

        assert p1 != p2
        assert ref1 != ref2

        sbx.write_file(p1, "file1.txt", "run1 data")
        assert (p1 / "file1.txt").exists()
        assert not (p2 / "file1.txt").exists()

        sbx.cleanup(p1)
        assert not p1.exists()
        assert p2.exists()


def test_sandbox_keeps_line_endings_exactly() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sbx = LocalWorkspaceProvider(base_dir=tmpdir)
        path, _ = sbx.allocate(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
        content = "line one\r\nline two\nline three\r\n"

        written = sbx.write_file(path, "app/layout.tsx", content)

        assert written.read_bytes() == content.encode("utf-8")  # no \r\r\n on Windows
        assert sbx.read_file(path, "app/layout.tsx") == content


# ============================================================
# 6. DETERMINISTIC ARTIFACT GENERATION & IDEMPOTENCY
# ============================================================


def test_deterministic_react_artifacts() -> None:
    proj_id = uuid.uuid4()
    asst_data = {
        "id": "asst-100",
        "name": "Store Assistant",
        "welcome_message": "Hello!",
        "brand_color": "#10B981",
        "text_color": "#FFFFFF",
        "position": "BOTTOM_RIGHT",
        "avatar_url": "https://example.com/pic.png",
        "starter_prompt": "Tell me more",
        "is_enabled": True,
    }

    # Generate once
    art1 = generate_artifacts(
        project_id=proj_id,
        assistant_data=asst_data,
        framework_skill_id="nextjs-app-router",
        widget_target_path="app/layout.tsx",
        existing_target_content=read_fixture("app/layout.tsx"),
    )

    # Generate twice with identical inputs
    art2 = generate_artifacts(
        project_id=proj_id,
        assistant_data=asst_data,
        framework_skill_id="nextjs-app-router",
        widget_target_path="app/layout.tsx",
        existing_target_content=read_fixture("app/layout.tsx"),
    )

    # Determinism: generate(A) == generate(A)
    assert art1 == art2
    assert "components/fussion/FussionAssistant.tsx" in art1
    assert "lib/fussion-assistant.ts" in art1
    assert "app/layout.tsx" in art1

    # Invariant: No secrets or raw tokens in config
    assert "ghp_" not in art1["lib/fussion-assistant.ts"]
    assert "Store Assistant" in art1["lib/fussion-assistant.ts"]
    assert "#10B981" in art1["lib/fussion-assistant.ts"]


def test_idempotent_react_layout_patching() -> None:
    initial_layout = (
        "import './globals.css';\n\n"
        "export default function RootLayout({ children }: { children: React.ReactNode }) {\n"
        "  return (\n"
        "    <html>\n"
        "      <body>\n"
        "        {children}\n"
        "      </body>\n"
        "    </html>\n"
        "  );\n"
        "}\n"
    )

    # First patch
    patched1 = patch_react_layout(initial_layout)
    assert "/* FUSSION-ASSISTANT:BEGIN-IMPORTS */" in patched1
    assert "/* FUSSION-ASSISTANT:END-IMPORTS */" in patched1
    assert "/* FUSSION-ASSISTANT:BEGIN-WIDGET */" in patched1
    assert patched1.count("import { FussionAssistant }") == 1
    assert patched1.count("<FussionAssistant />") == 1

    # Second patch against already-patched content (idempotency check)
    patched2 = patch_react_layout(patched1)
    # Must NOT duplicate imports or components
    assert patched2.count("/* FUSSION-ASSISTANT:BEGIN-IMPORTS */") == 1
    assert patched2.count("/* FUSSION-ASSISTANT:BEGIN-WIDGET */") == 1
    assert patched2.count("import { FussionAssistant }") == 1
    assert patched2.count("<FussionAssistant />") == 1
    assert patched2 == patched1


def test_deterministic_html_artifacts_and_idempotency() -> None:
    proj_id = uuid.uuid4()
    asst_data = {
        "id": "asst-200",
        "name": "HTML Bot",
        "brand_color": "#6366F1",
    }

    art = generate_artifacts(
        project_id=proj_id,
        assistant_data=asst_data,
        framework_skill_id="generic-html",
        widget_target_path="index.html",
        existing_target_content="<!DOCTYPE html>\n<html>\n<body>\n  <h1>Shop</h1>\n</body>\n</html>\n",
    )

    assert "fussion-assistant.js" in art
    assert "index.html" in art
    assert "<!-- FUSSION-ASSISTANT:BEGIN -->" in art["index.html"]

    # Idempotency check for HTML
    initial_html = "<html><body><h1>Shop</h1></body></html>"
    p1 = patch_html_index(initial_html)
    assert p1.count("<!-- FUSSION-ASSISTANT:BEGIN -->") == 1

    p2 = patch_html_index(p1)
    assert p2.count("<!-- FUSSION-ASSISTANT:BEGIN -->") == 1
    assert p2.count("fussion-assistant.js") == 1


# ============================================================
# 7. STATIC VALIDATOR & FORBIDDEN MODIFICATION REJECTION
# ============================================================


def test_static_validator_success_and_failures() -> None:
    plan = IntegrationPlanPayload(
        framework_skill_id="nextjs-app-router",
        files_to_create=["components/fussion/FussionAssistant.tsx", "lib/fussion-assistant.ts"],
        files_to_modify=["app/layout.tsx"],
    )

    original_layout = "export default function Layout({ children }) {\n  return <body>{children}</body>;\n}\n"
    originals = {"app/layout.tsx": original_layout}
    valid_files = {
        "components/fussion/FussionAssistant.tsx": "export function FussionAssistant() { return null; }",
        "lib/fussion-assistant.ts": 'export const fussionAssistantConfig = { "projectId": "p1", "assistantId": "a1", "brandColor": "#000", "position": "BOTTOM_RIGHT" };',
        "app/layout.tsx": patch_react_layout(original_layout),
    }

    # 1. Valid files pass
    issues = StaticValidator.validate("nextjs-app-router", plan, valid_files, originals)
    assert len(issues) == 0

    # 2. Forbidden unexpected file modification rejected
    forbidden_files = dict(valid_files)
    forbidden_files["package.json"] = '{"name": "hacked"}'
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate("nextjs-app-router", plan, forbidden_files, originals)
    assert "Forbidden files generated" in str(exc_info.value)

    # 3. Secret pattern in file rejected
    secret_files = dict(valid_files)
    secret_files["lib/fussion-assistant.ts"] += '\nconst token = "ghp_12345678901234567890123456789012";'
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate("nextjs-app-router", plan, secret_files, originals)
    assert "secret" in str(exc_info.value).lower()

    # 4. Absolute system path rejected
    system_path_files = dict(valid_files)
    system_path_files["lib/fussion-assistant.ts"] += '\nconst p = "C:\\Windows\\System32";'
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate("nextjs-app-router", plan, system_path_files, originals)
    assert "path" in str(exc_info.value).lower()

    # 5. Missing markers in modified file rejected
    missing_marker_files = dict(valid_files)
    missing_marker_files["app/layout.tsx"] = original_layout
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate("nextjs-app-router", plan, missing_marker_files, originals)
    assert "markers missing" in str(exc_info.value).lower()


# ============================================================
# 7b. PRESERVATION RULE — MODIFIED FILES KEEP THEIR CONTENT
# ============================================================

NEXTJS_PLAN = IntegrationPlanPayload(
    framework_skill_id="nextjs-app-router",
    files_to_create=["components/fussion/FussionAssistant.tsx", "lib/fussion-assistant.ts"],
    files_to_modify=["app/layout.tsx"],
)


# The hardcoded layout the defective pipeline used to write over customer files.
STUB_LAYOUT = (
    "export default function RootLayout({ children }: { children: React.ReactNode }) {\n"
    "  return (\n"
    '    <html lang="en">\n'
    "      <body>{children}</body>\n"
    "    </html>\n"
    "  );\n"
    "}\n"
)
ONE_LINE_LAYOUT = (
    "export default function RootLayout({ children }: { children: React.ReactNode }) "
    '{ return <html lang="en"><body>{children}</body></html>; }\n'
)
ADMIN_LAYOUT = (
    "export default function RootLayout({ children, user }) {\n"
    "  return (\n"
    "    <body>\n"
    "      {user.isAdmin && <AdminBar />}\n"
    "      {children}\n"
    "    </body>\n"
    "  );\n"
    "}\n"
)


def nextjs_artifacts(existing_layout: str) -> dict[str, str]:
    return generate_artifacts(
        project_id="proj-1",
        assistant_data={"id": "asst-1", "name": "Bot"},
        framework_skill_id="nextjs-app-router",
        widget_target_path="app/layout.tsx",
        existing_target_content=existing_layout,
    )


def validate_layout(files: dict[str, str], original_layout: str) -> list[str]:
    return StaticValidator.validate(
        "nextjs-app-router", NEXTJS_PLAN, files, {"app/layout.tsx": original_layout}
    )


def test_preservation_accepts_patch_of_real_layout() -> None:
    original = read_fixture("app/layout.tsx")
    assert validate_layout(nextjs_artifacts(original), original) == []


def test_preservation_rejects_stub_overwrite() -> None:
    # The CLAUDE.md §3.1 defect: the stub shares boilerplate lines with the real layout
    # (`return (`, `</html>`, `);`, `}`), so a "shares a fragment" rule would pass it.
    original = read_fixture("app/layout.tsx")
    with pytest.raises(StaticValidationError) as exc_info:
        validate_layout(nextjs_artifacts(STUB_LAYOUT), original)
    assert "outside Fussion-managed blocks at original line 1" in str(exc_info.value)


def test_preservation_rejects_deleted_line_and_reports_line_number() -> None:
    original = read_fixture("app/layout.tsx").replace("\r\n", "\n")
    analytics = '        <Analytics siteId="rr-storefront" />\n'
    files = nextjs_artifacts(original)
    files["app/layout.tsx"] = files["app/layout.tsx"].replace(analytics, "")
    expected_line = original.splitlines().index(analytics.rstrip("\n")) + 1

    with pytest.raises(StaticValidationError) as exc_info:
        validate_layout(files, original)
    message = str(exc_info.value)
    assert f"outside Fussion-managed blocks at original line {expected_line}" in message
    assert "rr-storefront" not in message  # never quote customer source


def test_preservation_requires_original_for_modified_file() -> None:
    files = nextjs_artifacts(read_fixture("app/layout.tsx"))
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate("nextjs-app-router", NEXTJS_PLAN, files, {})
    assert "original content was not read" in str(exc_info.value)


def test_preservation_accepts_repatch_of_already_integrated_layout() -> None:
    once = nextjs_artifacts(read_fixture("app/layout.tsx"))["app/layout.tsx"]
    twice = nextjs_artifacts(once)
    assert twice["app/layout.tsx"] == once
    assert validate_layout(twice, once) == []


def test_crlf_layout_keeps_crlf_and_passes_preservation() -> None:
    original = read_fixture("app/layout.tsx").replace("\r\n", "\n").replace("\n", "\r\n")
    files = nextjs_artifacts(original)
    patched = files["app/layout.tsx"]

    assert patched.count("\n") == patched.count("\r\n")  # no bare LF introduced
    assert validate_layout(files, original) == []


@pytest.mark.parametrize(
    ("original", "tamper", "expected_line"),
    [
        # A rewrite inside a customer line: every original character survives, in order.
        (ADMIN_LAYOUT, lambda s: s.replace("{user.isAdmin", "{!user.isAdmin"), 4),
        # A foreign script smuggled into an existing element.
        (
            read_fixture("app/layout.tsx"),
            lambda s: s.replace('siteId="rr-storefront" />', 'siteId="rr-storefront" src="https://evil.example/x.js" />'),
            27,
        ),
        # Content added outside Fussion-managed blocks.
        (
            ADMIN_LAYOUT,
            lambda s: s.replace("    </body>", '      <script src="https://evil.example/x.js"></script>\n    </body>'),
            6,
        ),
        # A small real layout overwritten by the stub: its characters all appear in the stub.
        (ONE_LINE_LAYOUT, lambda s: patch_react_layout(STUB_LAYOUT), 1),
    ],
    ids=["in-line-rewrite", "attribute-injection", "added-outside-blocks", "one-line-stub-overwrite"],
)
def test_preservation_rejects_changes_outside_managed_blocks(
    original: str, tamper: Callable[[str], str], expected_line: int
) -> None:
    files = nextjs_artifacts(original)
    files["app/layout.tsx"] = tamper(files["app/layout.tsx"])
    with pytest.raises(StaticValidationError) as exc_info:
        validate_layout(files, original)
    assert f"outside Fussion-managed blocks at original line {expected_line}" in str(exc_info.value)


def test_preservation_accepts_patch_of_one_line_layout() -> None:
    assert validate_layout(nextjs_artifacts(ONE_LINE_LAYOUT), ONE_LINE_LAYOUT) == []


def test_preservation_accepts_repatch_when_managed_block_content_changed() -> None:
    # A layout integrated by an older Fussion version: its managed block differs from today's.
    stale = patch_react_layout(ADMIN_LAYOUT).replace(
        "@/components/fussion/FussionAssistant", "@/components/fussion/OldAssistant"
    )
    files = nextjs_artifacts(stale)
    assert "OldAssistant" not in files["app/layout.tsx"]
    assert validate_layout(files, stale) == []


def test_preservation_ignores_line_endings_and_trailing_whitespace() -> None:
    original = read_fixture("app/layout.tsx").replace("\r\n", "\n")
    crlf_with_trailing_spaces = original.replace("\n", "  \r\n")
    files = nextjs_artifacts(original)  # LF output
    assert validate_layout(files, crlf_with_trailing_spaces) == []


# ============================================================
# 8. PIPELINE EXECUTION, COMMITS, PR CREATION & AUDIT
# ============================================================


@pytest.mark.asyncio
async def test_pipeline_execution_commit_and_pr(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "pipe_owner@example.com", "PipeOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Pipe Proj", "pipe-proj")

    mock_git = MockGitProvider()
    mock_git.add_file("fussion-org", "storefront", "app/layout.tsx", read_fixture("app/layout.tsx"))
    set_git_provider(mock_git)

    # 1. Configure website integration
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
            "default_branch": "main",
            "framework_skill_id": "nextjs-app-router",
            "widget_target_path": "app/layout.tsx",
            "github_token": "ghp_mock_token_for_test",
        },
    )

    # 2. Get deterministic plan
    plan_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/plan",
        headers=hdr,
    )
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert "components/fussion/FussionAssistant.tsx" in plan_data["files_to_create"]
    assert "app/layout.tsx" in plan_data["files_to_modify"]
    assert plan_data["target_status"] == "exists"

    # 3. Trigger integration run
    run_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs",
        headers=hdr,
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    run_id = run_data["id"]
    assert run_data["status"] == "PR_CREATED"
    assert run_data["commit_sha"] is not None
    assert run_data["pull_request_number"] is not None
    assert "fussion/integration/" in run_data["branch_name"]
    assert run_data["pull_request_url"] == f"https://github.com/fussion-org/storefront/pull/{run_data['pull_request_number']}"

    # 4. Verify branch and committed files in MockGitProvider
    branch_key = ("fussion-org", "storefront", run_data["branch_name"])
    assert branch_key in mock_git.branches
    committed = mock_git.committed_files[branch_key]
    assert "components/fussion/FussionAssistant.tsx" in committed
    assert "lib/fussion-assistant.ts" in committed
    assert "app/layout.tsx" in committed

    # 5. List runs
    list_runs = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs",
        headers=hdr,
    )
    assert list_runs.status_code == 200
    assert len(list_runs.json()) == 1

    # 6. Get run details
    run_detail = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs/{run_id}",
        headers=hdr,
    )
    assert run_detail.status_code == 200
    assert run_detail.json()["id"] == run_id

    # 7. Run diff: served from the change set the run recorded at generation time, never re-derived
    # (C12, CLAUDE.md §3.7).
    diff_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs/{run_id}/diff",
        headers=hdr,
    )
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    by_path = {item["path"]: item for item in diff_data["files"]}
    assert by_path["app/layout.tsx"]["action"] == "modify"
    assert by_path["components/fussion/FussionAssistant.tsx"]["action"] == "create"
    # The stored diff is the real content the run committed, not a placeholder or a re-derived stub.
    created_diff = by_path["components/fussion/FussionAssistant.tsx"]["diff"]
    assert "+export" in created_diff and "FussionAssistant" in created_diff
    modified_diff = by_path["app/layout.tsx"]["diff"]
    assert modified_diff.startswith("--- a/app/layout.tsx")
    # The original content is the "before" side, and the widget import is the "after" side.
    assert 'import type { Metadata } from "next";' in modified_diff
    assert "FussionAssistant" in modified_diff

    # 8. Get PR info
    pr_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs/{run_id}/pull-request",
        headers=hdr,
    )
    assert pr_resp.status_code == 200
    assert pr_resp.json()["pull_request_number"] == run_data["pull_request_number"]

    # 9. Verify audit events recorded without secret leakage
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(AuditEvent).where(AuditEvent.project_id == uuid.UUID(proj_id))
        events = (await db.execute(stmt)).scalars().all()
        event_types = [e.event_type for e in events]
        assert "integration.created" in event_types
        assert "integration.run.started" in event_types
        assert "integration.run.validated" in event_types
        assert "integration.pull_request.created" in event_types
        for ev in events:
            # Assure no tokens or passwords in payload
            assert "ghp_" not in str(ev.payload)
            assert "encrypted_secrets" not in ev.payload


@pytest.mark.asyncio
async def test_pipeline_preserves_existing_layout_content(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "preserve_owner@example.com", "PreserveOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Preserve Proj", "preserve-proj")

    mock_git = MockGitProvider()
    load_distinctive_repo(mock_git, "rwenzori", "storefront")
    set_git_provider(mock_git)

    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "rwenzori",
            "repository_name": "storefront",
            "framework_skill_id": "nextjs-app-router",
            "widget_target_path": "app/layout.tsx",
        },
    )

    run_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs",
        headers=hdr,
    )
    assert run_resp.status_code == 201, run_resp.text
    run_data = run_resp.json()
    assert run_data["plan_summary"]["files_to_modify"] == ["app/layout.tsx"]

    committed = mock_git.committed_files[("rwenzori", "storefront", run_data["branch_name"])]["app/layout.tsx"]

    # The customer's distinctive layout survives...
    for sentinel in (
        "FIXTURE-SENTINEL: Rwenzori Roasters root layout",
        'title: "Rwenzori Roasters | Single-origin coffee from Fort Portal"',
        '<CartProvider currency="UGX">',
        '<Analytics siteId="rr-storefront" />',
    ):
        assert sentinel in committed, f"customer content lost: {sentinel!r}"
    committed_lines = {line.rstrip() for line in committed.splitlines()}
    lost = [line for line in read_fixture("app/layout.tsx").splitlines() if line.rstrip() not in committed_lines]
    assert lost == []

    # ...and the widget is added to it.
    assert "<FussionAssistant />" in committed


@pytest.mark.asyncio
async def test_missing_target_is_refused_not_created(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "refuse_owner@example.com", "RefuseOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Refuse Proj", "refuse-proj")
    base = f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"

    mock_git = MockGitProvider()
    load_distinctive_repo(mock_git, "rwenzori", "storefront")
    set_git_provider(mock_git)

    # The repo keeps its layout at app/layout.tsx; the user typed a src/ path that does not exist.
    await client.post(
        base,
        headers=hdr,
        json={
            "repository_owner": "rwenzori",
            "repository_name": "storefront",
            "framework_skill_id": "nextjs-app-router",
            "widget_target_path": "src/app/layout.tsx",
        },
    )

    # The preview is where the wrong path is discovered.
    plan_data = (await client.get(f"{base}/plan", headers=hdr)).json()
    assert plan_data["target_status"] == "missing"
    assert "src/app/layout.tsx" in plan_data["files_to_modify"]
    assert "src/app/layout.tsx" not in plan_data["files_to_create"]
    assert any("was not found" in w for w in plan_data["warnings"])

    # The run is refused — distinct from a crash — before any branch or commit exists.
    run_resp = await client.post(f"{base}/runs", headers=hdr)
    assert run_resp.status_code == 422
    detail = run_resp.json()["detail"]
    assert detail.startswith("Integration refused:")
    assert "was not found on branch 'main'" in detail
    assert not any(b.startswith("fussion/") for (o, r, b) in mock_git.branches if o == "rwenzori")
    assert mock_git.committed_files == {}

    runs = (await client.get(f"{base}/runs", headers=hdr)).json()
    assert runs[0]["status"] == "FAILED"
    assert runs[0]["plan_summary"]["target_status"] == "missing"
    assert runs[0]["plan_summary"]["base_sha"] == mock_git.branches[("rwenzori", "storefront", "main")]

    # A run with no change set falls back to its recorded plan paths and a placeholder — it never
    # re-derives content from the current configuration (C12).
    diff = await client.get(f"{base}/runs/{runs[0]['id']}/diff", headers=hdr)
    assert diff.status_code == 200
    item = {f["path"]: f for f in diff.json()["files"]}["src/app/layout.tsx"]
    assert item["action"] == "modify"
    assert "no change set" in item["diff"].lower()

    async with get_session_factory()() as db:
        stmt = select(AuditEvent.event_type).where(AuditEvent.project_id == uuid.UUID(proj_id))
        event_types = (await db.execute(stmt)).scalars().all()
    assert "integration.run.refused" in event_types
    assert "integration.run.failed" not in event_types


class ConcurrentCommitGitProvider(MockGitProvider):
    """A customer commit lands on the default branch after Fussion read the target."""

    async def create_branch(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        base_sha: str,
        token: str | None = None,
    ) -> dict:
        head = self.branches[(owner, repo, base_branch)]
        customer_sha = "commit_customer_edit_during_run"
        self.trees[(owner, repo, customer_sha)] = {
            **self.trees[(owner, repo, head)],
            "app/layout.tsx": "// customer edit made while Fussion was running\n",
        }
        self.parents[customer_sha] = head
        self.branches[(owner, repo, base_branch)] = customer_sha
        # base_sha is what Fussion read; the branch must come from it, not from the moving head.
        return await super().create_branch(owner, repo, base_branch, new_branch, base_sha, token)


@pytest.mark.asyncio
async def test_pr_is_built_on_the_commit_that_was_read(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "race_owner@example.com", "RaceOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Race Proj", "race-proj")
    base = f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"

    mock_git = ConcurrentCommitGitProvider()
    load_distinctive_repo(mock_git, "rwenzori", "storefront")
    read_sha = mock_git.branches[("rwenzori", "storefront", "main")]
    set_git_provider(mock_git)
    await client.post(
        base,
        headers=hdr,
        json={"repository_owner": "rwenzori", "repository_name": "storefront"},
    )

    run_resp = await client.post(f"{base}/runs", headers=hdr)
    assert run_resp.status_code == 201, run_resp.text
    run_data = run_resp.json()

    # The integration commit's parent is the commit whose layout was read and patched, so the
    # customer's concurrent edit shows up as a merge conflict in the PR, not a silent revert.
    integration_head = mock_git.branches[("rwenzori", "storefront", run_data["branch_name"])]
    assert mock_git.parents[integration_head] == read_sha
    assert run_data["plan_summary"]["base_sha"] == read_sha


class FailingReadGitProvider(MockGitProvider):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def get_file_contents(self, *args: object, **kwargs: object) -> str | None:
        raise self.error


async def plan_preview_with(client: AsyncClient, provider: MockGitProvider, **integration: str) -> httpx.Response:
    token, _, org_id = await register_user(client, "preview_owner@example.com", "PreviewOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Preview Proj", "preview-proj")
    base = f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"

    set_git_provider(provider)
    await client.post(
        base,
        headers=hdr,
        json={"repository_owner": "fussion-org", "repository_name": "storefront", **integration},
    )
    return await client.get(f"{base}/plan", headers=hdr)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        GitHubUnavailableError("Could not reach GitHub while reading 'app/layout.tsx'", 503),
        GitHubUnavailableError("GitHub rate limit reached while reading 'app/layout.tsx'", 403),
    ],
    ids=["unreachable", "rate-limited"],
)
async def test_plan_preview_degrades_when_github_is_unavailable(
    client: AsyncClient, error: Exception
) -> None:
    plan_resp = await plan_preview_with(client, FailingReadGitProvider(error))

    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["target_status"] == "unknown"
    assert plan_data["files_to_modify"] == ["app/layout.tsx"]
    assert any("Could not confirm" in w for w in plan_data["warnings"])


@pytest.mark.asyncio
async def test_plan_preview_reports_configuration_errors(client: AsyncClient) -> None:
    error = GitHubAPIError("GitHub authentication error while reading 'app/layout.tsx': Bad credentials", 401)
    plan_resp = await plan_preview_with(client, FailingReadGitProvider(error))

    assert plan_resp.status_code == 400
    assert "Bad credentials" in plan_resp.json()["detail"]


@pytest.mark.asyncio
async def test_plan_preview_reports_an_invalid_path(client: AsyncClient) -> None:
    # A configuration error, not "unreachable": the preview names the real cause.
    #
    # The API now refuses an absolute path at configuration time (C11), so this seeds the corrupted
    # value directly to prove the plan endpoint still maps the provider's refusal to a 400 — the
    # same backstop shape as the run-refuses-a-protected-target test.
    token, _, org_id = await register_user(client, "preview_invalid@example.com", "PreviewInvalid")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Preview Invalid", "preview-invalid")
    base = f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"

    set_git_provider(MockGitProvider())
    created = await client.post(
        base,
        headers=hdr,
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    assert created.status_code == 201, created.text

    session_factory = get_session_factory()
    async with session_factory() as db:
        integration = (
            await db.execute(
                select(WebsiteIntegration).where(
                    WebsiteIntegration.project_id == uuid.UUID(proj_id)
                )
            )
        ).scalar_one()
        integration.widget_target_path = "/app/layout.tsx"
        await db.commit()

    plan_resp = await client.get(f"{base}/plan", headers=hdr)

    assert plan_resp.status_code == 400
    assert "Invalid repository file path '/app/layout.tsx'" in plan_resp.json()["detail"]


# ============================================================
# 8b. GIT PROVIDER — READING FILE CONTENTS
# ============================================================


def github_with(handler: Callable[[httpx.Request], httpx.Response]) -> GitHubProvider:
    return GitHubProvider(base_url="https://api.github.test", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_github_get_file_contents_decodes_file_at_ref() -> None:
    seen: dict[str, str] = {}
    raw = b"export default function Layout() {}\r\n// \xc3\xa9t\xc3\xa9\r\n"

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["ref"] = request.url.params["ref"]
        seen["auth"] = request.headers["Authorization"]
        # GitHub wraps base64 content at 60 characters.
        body = {"type": "file", "encoding": "base64", "content": base64.encodebytes(raw).decode()}
        return httpx.Response(200, json=body)

    content = await github_with(handler).get_file_contents(
        "acme", "site", "app/layout.tsx", ref="release/2026", token="tok"
    )

    assert content == raw.decode("utf-8")  # CRLF and non-ASCII preserved exactly
    assert seen == {
        "path": "/repos/acme/site/contents/app/layout.tsx",
        "ref": "release/2026",
        "auth": "Bearer tok",
    }


def respond(status: int, body: object = None, headers: dict[str, str] | None = None) -> Callable:
    return lambda request: httpx.Response(status, json=body, headers=headers)


def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "message", "transient"),
    [
        # Configuration problems the user must fix: reported as-is, never retried.
        (respond(200, [{"type": "file", "name": "layout.tsx"}]), "not a regular file", False),
        (respond(200, {"type": "file", "encoding": "none", "content": ""}), "too large", False),
        (respond(200, {"type": "file", "encoding": "base64", "content": "//79"}), "not a UTF-8", False),
        (respond(401, {"message": "Bad credentials"}), "authentication error", False),
        (respond(403, {"message": "Resource not accessible"}), "authentication error", False),
        # Transient: GitHub cannot answer right now.
        (respond(403, {"message": "API rate limit exceeded"}, {"x-ratelimit-remaining": "0"}), "rate limit", True),
        (respond(403, {"message": "secondary limit"}, {"retry-after": "60"}), "rate limit", True),
        (respond(429, {"message": "Too many requests"}), "rate limit", True),
        (respond(502, {"message": "Bad gateway"}), "unavailable", True),
        (lambda request: httpx.Response(200, text="<html>proxy</html>"), "unreadable response", True),
        (unreachable, "Could not reach GitHub", True),
    ],
    ids=[
        "directory", "over-1mb", "binary", "unauthorized", "forbidden",
        "rate-limit-403", "secondary-rate-limit", "429", "5xx", "non-json", "network",
    ],
)
async def test_github_get_file_contents_classifies_errors(
    handler: Callable, message: str, transient: bool
) -> None:
    with pytest.raises(GitHubAPIError) as exc_info:
        await github_with(handler).get_file_contents("acme", "site", "app/layout.tsx", ref="main")
    assert message in str(exc_info.value)
    assert isinstance(exc_info.value, GitHubUnavailableError) is transient


@pytest.mark.asyncio
async def test_github_branch_head_and_create_branch_at_pinned_sha() -> None:
    requests: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read()) if request.read() else {}
        requests.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json={"object": {"sha": "sha_current_head"}})
        return httpx.Response(201, json={"ref": "refs/heads/fussion/x"})

    provider = github_with(handler)
    assert await provider.get_branch_head("acme", "site", "release/2026") == "sha_current_head"
    assert requests[-1][:2] == ("GET", "/repos/acme/site/git/ref/heads/release/2026")

    # With a pinned SHA the branch is created there, without re-resolving the moving head.
    requests.clear()
    await provider.create_branch("acme", "site", "main", "fussion/x", base_sha="sha_read_earlier")
    assert requests == [
        ("POST", "/repos/acme/site/git/refs", {"ref": "refs/heads/fussion/x", "sha": "sha_read_earlier"})
    ]


def providers_for_contract() -> list[object]:
    mock = MockGitProvider()
    mock.add_repository("acme", "site")
    return [github_with(lambda request: httpx.Response(404, json={"message": "Not Found"})), mock]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", providers_for_contract(), ids=["github", "mock"])
async def test_get_file_contents_missing_file_is_none(provider: GitProvider) -> None:
    assert await provider.get_file_contents("acme", "site", "app/layout.tsx", ref="main") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", providers_for_contract(), ids=["github", "mock"])
async def test_get_branch_head_missing_branch_raises(provider: GitProvider) -> None:
    with pytest.raises(GitHubAPIError) as exc_info:
        await provider.get_branch_head("acme", "site", "no-such-branch")
    assert "Branch 'no-such-branch' not found" in str(exc_info.value)
    assert not isinstance(exc_info.value, GitHubUnavailableError)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", providers_for_contract(), ids=["github", "mock"])
@pytest.mark.parametrize(
    "path", ["", "../secrets.txt", "app/../../x", "/app/layout.tsx", "app\\layout.tsx", "app//x"]
)
async def test_get_file_contents_rejects_unsafe_paths(provider: GitProvider, path: str) -> None:
    with pytest.raises(GitHubAPIError) as exc_info:
        await provider.get_file_contents("acme", "site", path, ref="main")
    assert "Invalid repository file path" in str(exc_info.value)


@pytest.mark.asyncio
async def test_github_unsafe_path_makes_no_request() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(GitHubAPIError):
        await github_with(handler).get_file_contents("acme", "site", "../../user", ref="main")
    assert calls == []


# ============================================================
# 9. PIPELINE CANCELLATION & CASCADE DELETION
# ============================================================


@pytest.mark.asyncio
async def test_run_cancellation(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "cancel_owner@example.com", "CancelOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Cancel Proj", "cancel-proj")

    mock_git = MockGitProvider()
    set_git_provider(mock_git)

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
        },
    )
    integ_id = create_resp.json()["id"]

    # Insert a simulated RUNNING run in DB
    session_factory = get_session_factory()
    run_id = uuid.uuid4()
    async with session_factory() as db:
        run = IntegrationRun(
            id=run_id,
            integration_id=uuid.UUID(integ_id),
            status=IntegrationRunStatus.RUNNING,
            branch_name="fussion/integration/manual",
            sandbox_ref="sbx-manual",
        )
        db.add(run)
        await db.commit()

    # Cancel the run via API
    cancel_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs/{run_id}/cancel",
        headers=hdr,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_project_cascade_deletion(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "casc_integ_owner@example.com", "CascOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Casc Proj", "casc-proj")

    mock_git = MockGitProvider()
    mock_git.add_file("fussion-org", "storefront", "app/layout.tsx", read_fixture("app/layout.tsx"))
    set_git_provider(mock_git)

    # 1. Create integration & run
    integ_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    integ_id = integ_resp.json()["id"]

    run_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs",
        headers=hdr,
    )
    run_id = run_resp.json()["id"]

    # 2. Delete project
    del_p = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}",
        headers=hdr,
    )
    assert del_p.status_code == 204

    # 3. Verify project, integration, and runs are all cascade deleted
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt_p = select(Project).where(Project.id == uuid.UUID(proj_id))
        assert (await db.execute(stmt_p)).scalar_one_or_none() is None

        stmt_i = select(WebsiteIntegration).where(WebsiteIntegration.id == uuid.UUID(integ_id))
        assert (await db.execute(stmt_i)).scalar_one_or_none() is None

        stmt_r = select(IntegrationRun).where(IntegrationRun.id == uuid.UUID(run_id))
        assert (await db.execute(stmt_r)).scalar_one_or_none() is None
