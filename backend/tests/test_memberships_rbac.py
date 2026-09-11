import pytest
from httpx import AsyncClient


async def register(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
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


@pytest.mark.asyncio
async def test_rbac_permissions_and_invariants(client: AsyncClient):
    # Setup owner, admin, member, viewer
    owner_token, _owner_id, org_id = await register(client, "owner@example.com", "Owner")
    admin_token, _admin_id, _ = await register(client, "admin@example.com", "Admin")
    member_token, _member_id, _ = await register(client, "member@example.com", "Member")
    viewer_token, _viewer_id, _ = await register(client, "viewer@example.com", "Viewer")

    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    admin_hdr = {"Authorization": f"Bearer {admin_token}"}
    member_hdr = {"Authorization": f"Bearer {member_token}"}
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}

    # Owner adds Admin, Member, Viewer to org
    res_admin = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "admin@example.com", "role": "ADMIN"},
    )
    assert res_admin.status_code == 201
    admin_mem_id = res_admin.json()["id"]

    res_member = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "member@example.com", "role": "MEMBER"},
    )
    assert res_member.status_code == 201


    res_viewer = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=owner_hdr,
        json={"email": "viewer@example.com", "role": "VIEWER"},
    )
    assert res_viewer.status_code == 201
    viewer_mem_id = res_viewer.json()["id"]

    # 1. Viewer cannot create projects
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=viewer_hdr,
        json={"name": "Viewer Project"},
    )
    assert resp.status_code == 403

    # 2. Viewer cannot invite members
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=viewer_hdr,
        json={"email": "someone@example.com", "role": "MEMBER"},
    )
    assert resp.status_code == 403

    # 3. Member cannot invite members
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=member_hdr,
        json={"email": "someone@example.com", "role": "MEMBER"},
    )
    assert resp.status_code == 403

    # 4. Member cannot change roles
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{viewer_mem_id}",
        headers=member_hdr,
        json={"role": "ADMIN"},
    )
    assert resp.status_code == 403

    # 5. Admin can create projects
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=admin_hdr,
        json={"name": "Admin Project"},
    )
    assert resp.status_code == 201

    # 6. Admin cannot change roles
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{viewer_mem_id}",
        headers=admin_hdr,
        json={"role": "MEMBER"},
    )
    assert resp.status_code == 403

    # 7. Admin cannot remove OWNER
    owner_mem_id = (await client.get(f"/api/v1/organizations/{org_id}/members", headers=owner_hdr)).json()[0]["id"]
    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{owner_mem_id}",
        headers=admin_hdr,
    )
    assert resp.status_code == 403
    assert "Administrators cannot remove an organization OWNER" in resp.json()["detail"]

    # 8. Last OWNER cannot be removed or demoted
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{owner_mem_id}",
        headers=owner_hdr,
        json={"role": "ADMIN"},
    )
    assert resp.status_code == 400
    assert "last OWNER" in resp.json()["detail"]

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{owner_mem_id}",
        headers=owner_hdr,
    )
    assert resp.status_code == 400
    assert "last OWNER" in resp.json()["detail"]

    # 9. Owner can promote another user to OWNER, then demotion succeeds
    resp_promote = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{admin_mem_id}",
        headers=owner_hdr,
        json={"role": "OWNER"},
    )
    assert resp_promote.status_code == 200
    assert resp_promote.json()["role"] == "OWNER"

    # Now there are 2 owners, original owner demotion succeeds
    resp_demote = await client.patch(
        f"/api/v1/organizations/{org_id}/members/{owner_mem_id}",
        headers=owner_hdr,
        json={"role": "ADMIN"},
    )
    assert resp_demote.status_code == 200
    assert resp_demote.json()["role"] == "ADMIN"
