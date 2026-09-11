import pytest
from httpx import AsyncClient


async def register_user(client: AsyncClient, email: str, name: str, org_name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": org_name,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    orgs_resp = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_resp.json()[0]["id"]
    return token, org_id


@pytest.mark.asyncio
async def test_project_crud_and_organization_scoped_slugs(client: AsyncClient):
    token_a, org_a_id = await register_user(client, "alice_proj@example.com", "Alice", "Org Alpha")
    token_b, org_b_id = await register_user(client, "bob_proj@example.com", "Bob", "Org Beta")

    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    # Org A creates project with slug "website"
    resp_a = await client.post(
        f"/api/v1/organizations/{org_a_id}/projects",
        headers=hdr_a,
        json={"name": "Alpha Website", "slug": "website", "description": "Alpha marketing site"},
    )
    assert resp_a.status_code == 201
    proj_a = resp_a.json()
    assert proj_a["slug"] == "website"
    assert proj_a["organization_id"] == org_a_id

    # Org B creates project with identical slug "website" -> ALLOWED (slug unique per org)
    resp_b = await client.post(
        f"/api/v1/organizations/{org_b_id}/projects",
        headers=hdr_b,
        json={"name": "Beta Website", "slug": "website", "description": "Beta marketing site"},
    )
    assert resp_b.status_code == 201
    proj_b = resp_b.json()
    assert proj_b["slug"] == "website"
    assert proj_b["organization_id"] == org_b_id

    # Duplicate slug inside the SAME organization -> 400 REJECTED
    resp_dup = await client.post(
        f"/api/v1/organizations/{org_a_id}/projects",
        headers=hdr_a,
        json={"name": "Another Alpha Site", "slug": "website"},
    )
    assert resp_dup.status_code == 400
    assert "already taken" in resp_dup.json()["detail"]

    # List projects in Org A
    list_resp = await client.get(f"/api/v1/organizations/{org_a_id}/projects", headers=hdr_a)
    assert list_resp.status_code == 200
    projects_list = list_resp.json()
    assert len(projects_list) == 1
    assert projects_list[0]["id"] == proj_a["id"]


@pytest.mark.asyncio
async def test_critical_multi_tenant_isolation(client: AsyncClient):
    """
    Mandatory Section 27 Critical Multi-Tenant Security Test:
    User A / Org A / Project A vs User B / Org B / Project B
    """
    token_a, org_a_id = await register_user(client, "user_a@example.com", "User A", "Organization A")
    token_b, org_b_id = await register_user(client, "user_b@example.com", "User B", "Organization B")

    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    # Project A created in Org A
    res_proj_a = await client.post(
        f"/api/v1/organizations/{org_a_id}/projects",
        headers=hdr_a,
        json={"name": "Project A", "slug": "proj-a"},
    )
    assert res_proj_a.status_code == 201
    proj_a_id = res_proj_a.json()["id"]

    # Project B created in Org B
    res_proj_b = await client.post(
        f"/api/v1/organizations/{org_b_id}/projects",
        headers=hdr_b,
        json={"name": "Project B", "slug": "proj-b"},
    )
    assert res_proj_b.status_code == 201
    proj_b_id = res_proj_b.json()["id"]

    # 1. User A -> Project A = ALLOWED
    get_a_a = await client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}", headers=hdr_a)
    assert get_a_a.status_code == 200
    assert get_a_a.json()["id"] == proj_a_id

    # 2. User B -> Project B = ALLOWED
    get_b_b = await client.get(f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}", headers=hdr_b)
    assert get_b_b.status_code == 200
    assert get_b_b.json()["id"] == proj_b_id

    # 3. User A -> Project B via Org A URL = DENIED (404 - Project not found in Org A)
    get_a_b = await client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_b_id}", headers=hdr_a)
    assert get_a_b.status_code == 404

    # 4. User B -> Project A via Org B URL = DENIED (404 - Project not found in Org B)
    get_b_a = await client.get(f"/api/v1/organizations/{org_b_id}/projects/{proj_a_id}", headers=hdr_b)
    assert get_b_a.status_code == 404

    # 5. User A -> Org B URL directly: /organizations/{OrgB}/projects/{ProjectB} = DENIED (404 - User A has no membership in Org B)
    tamper_a = await client.get(f"/api/v1/organizations/{org_b_id}/projects/{proj_b_id}", headers=hdr_a)
    assert tamper_a.status_code == 404

    # 6. User B -> Org A URL directly: /organizations/{OrgA}/projects/{ProjectA} = DENIED (404 - User B has no membership in Org A)
    tamper_b = await client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_a_id}", headers=hdr_b)
    assert tamper_b.status_code == 404
