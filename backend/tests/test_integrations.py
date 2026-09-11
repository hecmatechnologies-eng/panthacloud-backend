import pytest
from httpx import AsyncClient

from app.core.secrets import SecretStore


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


@pytest.mark.asyncio
async def test_secret_store_encryption_and_decryption():
    store = SecretStore()
    payload = {"github_token": "ghp_secret1234567890", "client_secret": "my-client-secret"}
    encrypted = store.encrypt(payload)
    assert isinstance(encrypted, str)
    assert "ghp_secret" not in encrypted

    decrypted = store.decrypt(encrypted)
    assert decrypted == payload


@pytest.mark.asyncio
async def test_integration_crud_and_secret_redaction(client: AsyncClient):
    token, _, org_id = await register_user(client, "integ_owner@example.com", "IntegOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Portal", "portal")

    # 1. Create integration with sensitive secrets
    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=hdr,
        json={
            "name": "Production GitHub",
            "provider": "github",
            "configuration": {"repo": "fussion-org/website", "branch": "main"},
            "secrets": {"token": "ghp_real_secret_token_abc123"},
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["name"] == "Production GitHub"
    assert data["provider"] == "github"
    assert data["status"] == "ACTIVE"  # Status transitions to ACTIVE when credentials supplied
    assert data["configuration"]["repo"] == "fussion-org/website"
    assert data["has_credentials"] is True
    # Verify strict secret redaction
    assert "secrets" not in data
    assert "encrypted_secrets" not in data
    assert "token" not in str(data)

    integ_id = data["id"]

    # 2. Retrieve integration
    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == integ_id
    assert "encrypted_secrets" not in get_resp.json()

    # 3. List integrations
    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=hdr,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == integ_id

    # 4. Duplicate integration name in same project is rejected
    dup_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=hdr,
        json={
            "name": "Production GitHub",
            "provider": "github",
        },
    )
    assert dup_resp.status_code == 400
    assert "already exists" in dup_resp.json()["detail"]

    # 5. Update configuration and status
    update_resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
        json={
            "status": "DISCONNECTED",
            "configuration": {"branch": "release"},
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "DISCONNECTED"
    assert update_resp.json()["configuration"]["branch"] == "release"
    assert update_resp.json()["configuration"]["repo"] == "fussion-org/website"

    # 6. Delete integration
    del_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
    )
    assert del_resp.status_code == 204

    # 7. Verify deletion
    verify_resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
    )
    assert verify_resp.status_code == 404


@pytest.mark.asyncio
async def test_integration_lifecycle_transitions(client: AsyncClient):
    token, _, org_id = await register_user(client, "lifecycle@example.com", "Lifecycle")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Lifecycle Proj", "lifecycle-proj")

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=hdr,
        json={"name": "Webhook Hook", "provider": "webhook", "status": "PENDING"},
    )
    integ_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "PENDING"

    # Valid transition: PENDING -> ACTIVE
    p1 = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
        json={"status": "ACTIVE"},
    )
    assert p1.status_code == 200
    assert p1.json()["status"] == "ACTIVE"

    # Valid transition: ACTIVE -> DISCONNECTED
    p2 = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
        json={"status": "DISCONNECTED"},
    )
    assert p2.status_code == 200
    assert p2.json()["status"] == "DISCONNECTED"

    # Invalid transition: DISCONNECTED directly to ERROR via user action
    p_invalid = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=hdr,
        json={"status": "ERROR"},
    )
    assert p_invalid.status_code == 400
    assert "Invalid state transition" in p_invalid.json()["detail"]


@pytest.mark.asyncio
async def test_integration_rbac(client: AsyncClient):
    # Setup owner, admin, member, viewer
    owner_token, _, org_id = await register_user(client, "rbac_owner@example.com", "RbacOwner")
    admin_token, _, _ = await register_user(client, "rbac_admin@example.com", "RbacAdmin")
    member_token, _, _ = await register_user(client, "rbac_member@example.com", "RbacMember")
    viewer_token, _, _ = await register_user(client, "rbac_viewer@example.com", "RbacViewer")

    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    admin_hdr = {"Authorization": f"Bearer {admin_token}"}
    member_hdr = {"Authorization": f"Bearer {member_token}"}
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}

    # Add roles to org
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "rbac_admin@example.com", "role": "ADMIN"},
    )
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "rbac_member@example.com", "role": "MEMBER"},
    )
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "rbac_viewer@example.com", "role": "VIEWER"},
    )

    proj_id = await create_project(client, owner_token, org_id, "RBAC Proj", "rbac-proj")

    # 1. VIEWER cannot create integration
    r_v_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=viewer_hdr,
        json={"name": "Viewer Git", "provider": "gitlab"},
    )
    assert r_v_create.status_code == 403

    # 2. MEMBER CAN create integration
    r_m_create = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=member_hdr,
        json={"name": "Member Git", "provider": "gitlab"},
    )
    assert r_m_create.status_code == 201
    integ_id = r_m_create.json()["id"]

    # 3. VIEWER CAN view integration
    r_v_view = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=viewer_hdr,
    )
    assert r_v_view.status_code == 200

    # 4. MEMBER CAN modify integration
    r_m_patch = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=member_hdr,
        json={"name": "Member Git Renamed"},
    )
    assert r_m_patch.status_code == 200

    # 5. MEMBER CANNOT delete integration
    r_m_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=member_hdr,
    )
    assert r_m_del.status_code == 403

    # 6. ADMIN CAN delete integration
    r_a_del = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
        headers=admin_hdr,
    )
    assert r_a_del.status_code == 204


@pytest.mark.asyncio
async def test_mandatory_multi_tenant_integration_isolation(client: AsyncClient):
    """
    Mandatory Section 19 Multi-Tenant Integration Security Test:
    User A / Org A / Project A / Integration A vs User B / Org B / Project B / Integration B
    """
    token_a, _, org_a_id = await register_user(client, "iso_a@example.com", "IsoA")
    token_b, _, org_b_id = await register_user(client, "iso_b@example.com", "IsoB")

    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    proj_a_id = await create_project(client, token_a, org_a_id, "Proj A", "proj-a")
    proj_b_id = await create_project(client, token_b, org_b_id, "Proj B", "proj-b")

    res_a = await client.post(
        f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/integrations",
        headers=hdr_a,
        json={"name": "GitHub A", "provider": "github"},
    )
    assert res_a.status_code == 201
    integ_a_id = res_a.json()["id"]

    res_b = await client.post(
        f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}/integrations",
        headers=hdr_b,
        json={"name": "GitHub B", "provider": "github"},
    )
    assert res_b.status_code == 201
    integ_b_id = res_b.json()["id"]

    # 1. User A -> Integration A = ALLOWED
    assert (
        await client.get(
            f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/integrations/{integ_a_id}",
            headers=hdr_a,
        )
    ).status_code == 200

    # 2. User B -> Integration B = ALLOWED
    assert (
        await client.get(
            f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}/integrations/{integ_b_id}",
            headers=hdr_b,
        )
    ).status_code == 200

    # 3. User A -> Integration B (via Org A / Proj A URL) = DENIED (404)
    assert (
        await client.get(
            f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/integrations/{integ_b_id}",
            headers=hdr_a,
        )
    ).status_code == 404

    # 4. User B -> Integration A (via Org B / Proj B URL) = DENIED (404)
    assert (
        await client.get(
            f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}/integrations/{integ_a_id}",
            headers=hdr_b,
        )
    ).status_code == 404

    # 5. User A -> Direct URL Tampering to Org B / Proj B = DENIED (404)
    assert (
        await client.get(
            f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}/integrations/{integ_b_id}",
            headers=hdr_a,
        )
    ).status_code == 404

    # 6. User B -> Direct URL Tampering to Org A / Proj A = DENIED (404)
    assert (
        await client.get(
            f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}/integrations/{integ_a_id}",
            headers=hdr_b,
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_project_deletion_cascades_integrations(client: AsyncClient):
    token, _, org_id = await register_user(client, "casc_owner@example.com", "CascOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Cascade Proj", "cascade-proj")

    res = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations",
        headers=hdr,
        json={"name": "Cascade Integration", "provider": "webhook"},
    )
    assert res.status_code == 201
    integ_id = res.json()["id"]

    # Delete project
    del_proj = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}",
        headers=hdr,
    )
    assert del_proj.status_code == 204

    # Project is gone
    assert (await client.get(f"/api/v1/organizations/{org_id}/projects/{proj_id}", headers=hdr)).status_code == 404

    # Integration is gone as well
    assert (
        await client.get(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/integrations/{integ_id}",
            headers=hdr,
        )
    ).status_code == 404
