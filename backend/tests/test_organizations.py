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


# ============================================================
# Deleting an organization
# ============================================================


@pytest.mark.asyncio
async def test_owner_deletes_the_organization_and_everything_beneath_it(client: AsyncClient):
    """Deletion cascades: memberships, projects, and their integrations, assistants and knowledge."""
    import uuid

    from sqlalchemy import func, select

    from app.core.database import get_session_factory
    from app.models.project import Project

    auth = await register_user(client, "doomed@example.com", "Doomed", "Doomed Org")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": "Doomed Project", "slug": "doomed-project"},
    )
    assert project.status_code == 201

    deleted = await client.delete(f"/api/v1/organizations/{org_id}", headers=headers)

    assert deleted.status_code == 204
    # Gone from the caller's own list, and gone as a row.
    assert (await client.get("/api/v1/organizations", headers=headers)).json() == []
    assert (await client.get(f"/api/v1/organizations/{org_id}", headers=headers)).status_code == 404

    session_factory = get_session_factory()
    async with session_factory() as db:
        remaining = (
            await db.execute(
                select(func.count())
                .select_from(Project)
                .where(Project.organization_id == uuid.UUID(org_id))
            )
        ).scalar_one()
    assert remaining == 0


@pytest.mark.asyncio
async def test_a_foreign_organization_cannot_be_deleted(client: AsyncClient):
    """404, not 403: a stranger must not learn that the organization exists."""
    victim = await register_user(client, "victim@example.com", "Victim", "Victim Org")
    victim_headers = {"Authorization": f"Bearer {victim['access_token']}"}
    victim_org = (await client.get("/api/v1/organizations", headers=victim_headers)).json()[0]["id"]

    attacker = await register_user(client, "attacker@example.com", "Attacker", "Attacker Org")
    attacker_headers = {"Authorization": f"Bearer {attacker['access_token']}"}

    resp = await client.delete(
        f"/api/v1/organizations/{victim_org}", headers=attacker_headers
    )

    assert resp.status_code == 404
    # And it is still there.
    assert (
        await client.get(f"/api/v1/organizations/{victim_org}", headers=victim_headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_a_member_cannot_delete_the_organization(client: AsyncClient):
    from app.models.membership import RoleEnum

    owner = await register_user(client, "del_owner@example.com", "DelOwner", "Del Org")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    org_id = (await client.get("/api/v1/organizations", headers=owner_headers)).json()[0]["id"]

    member = await register_user(client, "del_member@example.com", "DelMember", "Member Org")
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    invited = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_headers,
        json={"email": "del_member@example.com", "role": RoleEnum.MEMBER.value},
    )
    assert invited.status_code == 201, invited.text

    resp = await client.delete(f"/api/v1/organizations/{org_id}", headers=member_headers)

    assert resp.status_code == 403
