import pytest
from httpx import AsyncClient


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
) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "provider": provider,
            "configuration": {"repo": f"fussion-org/{name.lower()}"},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_repository_crud(client: AsyncClient):
    token, _, org_id = await register_user(client, "repocrud@example.com", "RepoUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Storefront", "storefront")
    integ_id = await create_integration(client, token, org_id, proj_id, "Main GitHub", provider="github")

    # 1. Register repository
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "web-storefront",
            "full_name": "acme/web-storefront",
            "external_id": "gh-repo-1001",
            "default_branch": "main",
            "url": "https://github.com/acme/web-storefront",
            "metadata": {"language": "TypeScript", "visibility": "private"},
        },
    )
    assert create_resp.status_code == 201
    repo_data = create_resp.json()
    assert repo_data["name"] == "web-storefront"
    assert repo_data["full_name"] == "acme/web-storefront"
    assert repo_data["external_id"] == "gh-repo-1001"
    assert repo_data["provider"] == "github"
    assert repo_data["status"] == "PENDING"
    assert repo_data["metadata"]["language"] == "TypeScript"
    repo_id = repo_data["id"]

    # 2. Retrieve repository
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == repo_id
    assert get_resp.json()["external_id"] == "gh-repo-1001"

    # 3. List repositories
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
    )
    assert list_resp.status_code == 200
    repos = list_resp.json()
    assert len(repos) == 1
    assert repos[0]["id"] == repo_id

    # 4. Update repository metadata and status
    patch_resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
        json={
            "default_branch": "develop",
            "status": "CONNECTED",
            "metadata": {"framework": "Next.js"},
        },
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["default_branch"] == "develop"
    assert patched["status"] == "CONNECTED"
    assert patched["metadata"]["framework"] == "Next.js"
    assert patched["metadata"]["language"] == "TypeScript"

    # 5. Delete repository
    del_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
    )
    assert del_resp.status_code == 204

    # 6. Verify deletion
    verify_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
    )
    assert verify_resp.status_code == 404


@pytest.mark.asyncio
async def test_provider_compatibility_validation(client: AsyncClient):
    token, _, org_id = await register_user(client, "compat@example.com", "CompatUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Compat Project", "compat-proj")
    github_integ = await create_integration(client, token, org_id, proj_id, "GitHub App", provider="github")

    # Incompatible: GitHub integration + GitLab repository
    incompat_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": github_integ,
            "provider": "gitlab",
            "name": "gitlab-repo",
            "full_name": "acme/gitlab-repo",
            "external_id": "gl-123",
        },
    )
    assert incompat_resp.status_code == 400
    assert "incompatible" in incompat_resp.json()["detail"].lower()

    # Compatible: GitHub integration + GitHub repository
    compat_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": github_integ,
            "provider": "github",
            "name": "github-repo",
            "full_name": "acme/github-repo",
            "external_id": "gh-123",
        },
    )
    assert compat_resp.status_code == 201


@pytest.mark.asyncio
async def test_project_integration_relationship_validation(client: AsyncClient):
    token, _, org_id = await register_user(client, "projinteg@example.com", "ProjIntegUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_a = await create_project(client, token, org_id, "Project A", "proj-a")
    proj_b = await create_project(client, token, org_id, "Project B", "proj-b")

    # Integration B belongs strictly to Project B
    integ_b = await create_integration(client, token, org_id, proj_b, "Integ B", provider="github")

    # Attempt to register repo in Project A using Integration B
    cross_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_a}/repositories",
        headers=hdr,
        json={
            "integration_id": integ_b,
            "provider": "github",
            "name": "illegal-repo",
            "full_name": "acme/illegal",
            "external_id": "gh-999",
        },
    )
    assert cross_resp.status_code == 400
    assert "does not belong to this project" in cross_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_duplicate_external_id_rejection(client: AsyncClient):
    token, _, org_id = await register_user(client, "dup@example.com", "DupUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Dup Project", "dup-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Primary", provider="github")

    # Register first repository
    resp1 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "repo-one",
            "full_name": "acme/repo-one",
            "external_id": "gh-ext-42",
        },
    )
    assert resp1.status_code == 201

    # Attempt duplicate external_id on the same integration
    resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "repo-two",
            "full_name": "acme/repo-two",
            "external_id": "gh-ext-42",
        },
    )
    assert resp2.status_code == 400
    assert "already registered" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_repository_status_transitions(client: AsyncClient):
    token, _, org_id = await register_user(client, "status@example.com", "StatusUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Status Proj", "status-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "GitHub Integ", provider="github")

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "status-repo",
            "full_name": "acme/status-repo",
            "external_id": "gh-status-1",
        },
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "PENDING"

    # PENDING -> CONNECTED: Valid
    t1 = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
        json={"status": "CONNECTED"},
    )
    assert t1.status_code == 200
    assert t1.json()["status"] == "CONNECTED"

    # CONNECTED -> DISCONNECTED: Valid
    t2 = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
        json={"status": "DISCONNECTED"},
    )
    assert t2.status_code == 200
    assert t2.json()["status"] == "DISCONNECTED"

    # DISCONNECTED -> PENDING: Invalid state transition
    t3 = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
        json={"status": "PENDING"},
    )
    assert t3.status_code == 400
    assert "invalid state transition" in t3.json()["detail"].lower()


@pytest.mark.asyncio
async def test_repository_rbac(client: AsyncClient):
    # Setup Owner
    owner_token, _, org_id = await register_user(client, "owner_repo@example.com", "RepoOwner")
    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    proj_id = await create_project(client, owner_token, org_id, "RBAC Project", "rbac-proj")
    integ_id = await create_integration(client, owner_token, org_id, proj_id, "RBAC GitHub", provider="github")

    # Create Admin
    admin_reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "admin_repo@example.com", "password": "Password123!", "full_name": "RepoAdmin", "org_name": "A Org"},
    )
    admin_token = admin_reg.json()["access_token"]
    admin_hdr = {"Authorization": f"Bearer {admin_token}"}
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "admin_repo@example.com", "role": "ADMIN"},
    )

    # Create Member
    member_reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "member_repo@example.com", "password": "Password123!", "full_name": "RepoMember", "org_name": "M Org"},
    )
    member_token = member_reg.json()["access_token"]
    member_hdr = {"Authorization": f"Bearer {member_token}"}
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "member_repo@example.com", "role": "MEMBER"},
    )

    # Create Viewer
    viewer_reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "viewer_repo@example.com", "password": "Password123!", "full_name": "RepoViewer", "org_name": "V Org"},
    )
    viewer_token = viewer_reg.json()["access_token"]
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "viewer_repo@example.com", "role": "VIEWER"},
    )

    # VIEWER cannot create repository -> 403 Forbidden
    v_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=viewer_hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "viewer-repo",
            "full_name": "acme/viewer-repo",
            "external_id": "v-1",
        },
    )
    assert v_create.status_code == 403

    # MEMBER can create repository -> 201 Created
    m_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=member_hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "member-repo",
            "full_name": "acme/member-repo",
            "external_id": "m-1",
        },
    )
    assert m_create.status_code == 201
    repo_id = m_create.json()["id"]

    # VIEWER can view repository -> 200 OK
    v_view = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=viewer_hdr,
    )
    assert v_view.status_code == 200

    # VIEWER cannot update repository -> 403 Forbidden
    v_patch = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=viewer_hdr,
        json={"default_branch": "dev"},
    )
    assert v_patch.status_code == 403

    # MEMBER can update repository -> 200 OK
    m_patch = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=member_hdr,
        json={"default_branch": "staging"},
    )
    assert m_patch.status_code == 200

    # MEMBER cannot delete repository -> 403 Forbidden
    m_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=member_hdr,
    )
    assert m_del.status_code == 403

    # ADMIN can delete repository -> 204 No Content
    a_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=admin_hdr,
    )
    assert a_del.status_code == 204


@pytest.mark.asyncio
async def test_critical_multi_tenant_repository_isolation(client: AsyncClient):
    """
    Mandatory Section 15 & Section 20 Multi-Tenant Security Verification:
    User A (Org A, Proj A, Repo A) vs User B (Org B, Proj B, Repo B)
    Cross-tenant requests and URL tampering must return 404 Not Found.
    """
    # Tenant A
    token_a, _, org_a = await register_user(client, "tenant_a_repo@example.com", "Tenant A")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    proj_a = await create_project(client, token_a, org_a, "Project A", "proj-a")
    integ_a = await create_integration(client, token_a, org_a, proj_a, "GitHub A", provider="github")
    resp_repo_a = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories",
        headers=hdr_a,
        json={
            "integration_id": integ_a,
            "provider": "github",
            "name": "repo-a",
            "full_name": "org-a/repo-a",
            "external_id": "gh-a-100",
        },
    )
    assert resp_repo_a.status_code == 201
    repo_a = resp_repo_a.json()["id"]

    # Tenant B
    token_b, _, org_b = await register_user(client, "tenant_b_repo@example.com", "Tenant B")
    hdr_b = {"Authorization": f"Bearer {token_b}"}
    proj_b = await create_project(client, token_b, org_b, "Project B", "proj-b")
    integ_b = await create_integration(client, token_b, org_b, proj_b, "GitHub B", provider="github")
    resp_repo_b = await client.post(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/repositories",
        headers=hdr_b,
        json={
            "integration_id": integ_b,
            "provider": "github",
            "name": "repo-b",
            "full_name": "org-b/repo-b",
            "external_id": "gh-b-200",
        },
    )
    assert resp_repo_b.status_code == 201
    repo_b = resp_repo_b.json()["id"]

    # 1. Authorized access succeeds
    assert (
        await client.get(f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}", headers=hdr_a)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/organizations/{org_b}/projects/{proj_b}/repositories/{repo_b}", headers=hdr_b)
    ).status_code == 200

    # 2. Cross-tenant access under user's own org/project path returns 404 (repo not in project)
    assert (
        await client.get(f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_b}", headers=hdr_a)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/organizations/{org_b}/projects/{proj_b}/repositories/{repo_a}", headers=hdr_b)
    ).status_code == 404

    # 3. URL tampering: User A attempts direct access to Org B / Project B / Repo B returns 404 (tenant unresolvable)
    tamper_a = await client.get(
        f"/api/v1/organizations/{org_b}/projects/{proj_b}/repositories/{repo_b}",
        headers=hdr_a,
    )
    assert tamper_a.status_code == 404

    # 4. URL tampering: User B attempts direct access to Org A / Project A / Repo A returns 404
    tamper_b = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/repositories/{repo_a}",
        headers=hdr_b,
    )
    assert tamper_b.status_code == 404


@pytest.mark.asyncio
async def test_cascade_deletion(client: AsyncClient):
    token, _, org_id = await register_user(client, "cascade_repo@example.com", "CascadeUser")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Cascade Proj", "cascade-proj")
    integ_id = await create_integration(client, token, org_id, proj_id, "Cascade GitHub", provider="github")

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories",
        headers=hdr,
        json={
            "integration_id": integ_id,
            "provider": "github",
            "name": "cascade-repo",
            "full_name": "acme/cascade-repo",
            "external_id": "casc-1",
        },
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["id"]

    # Delete the parent integration -> Child repository should be cascade deleted
    del_integ = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
    )
    assert del_integ.status_code == 204

    # Verify repository is gone
    get_repo = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/repositories/{repo_id}",
        headers=hdr,
    )
    assert get_repo.status_code == 404
