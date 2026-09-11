import tempfile
import uuid

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
    WebsiteFramework,
    WebsiteIntegration,
)
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.artifacts import (
    generate_artifacts,
    patch_html_index,
    patch_react_layout,
)
from app.services.integration.github import MockGitProvider, set_git_provider
from app.services.integration.sandbox import SandboxManager, SandboxSecurityError
from app.services.integration.validation import StaticValidationError, StaticValidator


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
            "framework": "REACT_NEXTJS",
            "website_root_dir": "/",
            "widget_target_path": "app/layout.tsx",
            "github_token": raw_token,
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["repository_owner"] == "fussion-org"
    assert data["repository_name"] == "storefront"
    assert data["framework"] == "REACT_NEXTJS"
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
            "framework": "REACT_NEXTJS",
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
        sbx = SandboxManager(base_dir=tmpdir)
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
        sbx = SandboxManager(base_dir=tmpdir)
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
        framework=WebsiteFramework.REACT_NEXTJS,
        widget_target_path="app/layout.tsx",
    )

    # Generate twice with identical inputs
    art2 = generate_artifacts(
        project_id=proj_id,
        assistant_data=asst_data,
        framework=WebsiteFramework.REACT_NEXTJS,
        widget_target_path="app/layout.tsx",
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
        framework=WebsiteFramework.GENERIC_HTML,
        widget_target_path="index.html",
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
        framework=WebsiteFramework.REACT_NEXTJS,
        files_to_create=["components/fussion/FussionAssistant.tsx", "lib/fussion-assistant.ts"],
        files_to_modify=["app/layout.tsx"],
    )

    valid_files = {
        "components/fussion/FussionAssistant.tsx": "export function FussionAssistant() { return null; }",
        "lib/fussion-assistant.ts": 'export const fussionAssistantConfig = { "projectId": "p1", "assistantId": "a1", "brandColor": "#000", "position": "BOTTOM_RIGHT" };',
        "app/layout.tsx": "/* FUSSION-ASSISTANT:BEGIN */\nimport { FussionAssistant } from '@/components/fussion/FussionAssistant';\n/* FUSSION-ASSISTANT:END */",
    }

    # 1. Valid files pass
    issues = StaticValidator.validate(WebsiteFramework.REACT_NEXTJS, plan, valid_files)
    assert len(issues) == 0

    # 2. Forbidden unexpected file modification rejected
    forbidden_files = dict(valid_files)
    forbidden_files["package.json"] = '{"name": "hacked"}'
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate(WebsiteFramework.REACT_NEXTJS, plan, forbidden_files)
    assert "Forbidden files generated" in str(exc_info.value)

    # 3. Secret pattern in file rejected
    secret_files = dict(valid_files)
    secret_files["lib/fussion-assistant.ts"] += '\nconst token = "ghp_12345678901234567890123456789012";'
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate(WebsiteFramework.REACT_NEXTJS, plan, secret_files)
    assert "secret" in str(exc_info.value).lower()

    # 4. Absolute system path rejected
    system_path_files = dict(valid_files)
    system_path_files["lib/fussion-assistant.ts"] += '\nconst p = "C:\\Windows\\System32";'
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate(WebsiteFramework.REACT_NEXTJS, plan, system_path_files)
    assert "path" in str(exc_info.value).lower()

    # 5. Missing markers in modified file rejected
    missing_marker_files = dict(valid_files)
    missing_marker_files["app/layout.tsx"] = "export default function Layout() { return null; }"
    with pytest.raises(StaticValidationError) as exc_info:
        StaticValidator.validate(WebsiteFramework.REACT_NEXTJS, plan, missing_marker_files)
    assert "markers missing" in str(exc_info.value).lower()


# ============================================================
# 8. PIPELINE EXECUTION, COMMITS, PR CREATION & AUDIT
# ============================================================


@pytest.mark.asyncio
async def test_pipeline_execution_commit_and_pr(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "pipe_owner@example.com", "PipeOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Pipe Proj", "pipe-proj")

    mock_git = MockGitProvider()
    set_git_provider(mock_git)

    # 1. Configure website integration
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=hdr,
        json={
            "repository_owner": "fussion-org",
            "repository_name": "storefront",
            "default_branch": "main",
            "framework": "REACT_NEXTJS",
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

    # 7. Get run diff
    diff_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/runs/{run_id}/diff",
        headers=hdr,
    )
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert len(diff_data["files"]) >= 3

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
