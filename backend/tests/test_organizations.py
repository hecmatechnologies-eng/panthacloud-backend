import pytest
from httpx import AsyncClient


async def register_user(client: AsyncClient, email: str, name: str, org_name: str) -> dict:
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
    return resp.json()


@pytest.mark.asyncio
async def test_organization_creation_and_owner_assignment(client: AsyncClient):
    auth_data = await register_user(client, "founder@example.com", "Founder", "Default Org")
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a second organization explicitly
    resp = await client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Acme Ventures", "slug": "acme-ventures"},
    )
    assert resp.status_code == 201
    org = resp.json()
    assert org["name"] == "Acme Ventures"
    assert org["slug"] == "acme-ventures"
    org_id = org["id"]

    # Verify members of this newly created org lists founder as OWNER
    members_resp = await client.get(
        f"/api/v1/organizations/{org_id}/members",
        headers=headers,
    )
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["role"] == "OWNER"
    assert members[0]["user"]["email"] == "founder@example.com"


@pytest.mark.asyncio
async def test_organization_listing_scoped_to_memberships(client: AsyncClient):
    user_a = await register_user(client, "usera@example.com", "User A", "Org A")
    user_b = await register_user(client, "userb@example.com", "User B", "Org B")

    headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

    # User A lists orgs -> only sees Org A
    resp_a = await client.get("/api/v1/organizations", headers=headers_a)
    assert resp_a.status_code == 200
    orgs_a = resp_a.json()
    assert len(orgs_a) == 1
    assert orgs_a[0]["name"] == "Org A"

    # User B lists orgs -> only sees Org B
    resp_b = await client.get("/api/v1/organizations", headers=headers_b)
    assert resp_b.status_code == 200
    orgs_b = resp_b.json()
    assert len(orgs_b) == 1
    assert orgs_b[0]["name"] == "Org B"


@pytest.mark.asyncio
async def test_cross_tenant_organization_denial(client: AsyncClient):
    user_a = await register_user(client, "tenant_a@example.com", "Tenant A", "Org Alpha")
    user_b = await register_user(client, "tenant_b@example.com", "Tenant B", "Org Beta")

    headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

    orgs_a = (await client.get("/api/v1/organizations", headers=headers_a)).json()
    org_a_id = orgs_a[0]["id"]

    # User B attempts to access Org A -> 404 (not found / denied)
    resp = await client.get(f"/api/v1/organizations/{org_a_id}", headers=headers_b)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
