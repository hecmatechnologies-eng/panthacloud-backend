import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.assistant import Assistant
from app.models.project import Project


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
async def test_get_or_create_default_assistant(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst1@example.com", "Alice Asst1")
    project_id = await create_project(client, token, org_id, "Storefront Alpha", "storefront-alpha")

    # Access assistant endpoint for the first time
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Fussion Assistant"
    assert data["welcome_message"] == "Hi! How can I help you today?"
    assert data["brand_color"] == "#6366F1"
    assert data["text_color"] == "#FFFFFF"
    assert data["position"] == "BOTTOM_RIGHT"
    assert data["is_enabled"] is True
    assert data["project_id"] == project_id

    # Verify directly in database
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(Assistant).where(Assistant.project_id == uuid.UUID(project_id))
        result = await db.execute(stmt)
        asst_db = result.scalar_one_or_none()
        assert asst_db is not None
        assert asst_db.name == "Fussion Assistant"


@pytest.mark.asyncio
async def test_update_assistant_identity(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst2@example.com", "Alice Asst2")
    project_id = await create_project(client, token, org_id, "Storefront Beta", "storefront-beta")

    # Update identity fields
    resp = await client.put(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Boutique Concierge",
            "description": "Virtual stylist and shopping assistant",
            "welcome_message": "Welcome to our boutique! How may I style you today?",
            "starter_prompt": "What are your new arrivals?",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Boutique Concierge"
    assert data["description"] == "Virtual stylist and shopping assistant"
    assert data["welcome_message"] == "Welcome to our boutique! How may I style you today?"
    assert data["starter_prompt"] == "What are your new arrivals?"
    # Defaults preserved for unmentioned fields
    assert data["brand_color"] == "#6366F1"


@pytest.mark.asyncio
async def test_update_assistant_appearance_and_patch(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst3@example.com", "Alice Asst3")
    project_id = await create_project(client, token, org_id, "Storefront Gamma", "storefront-gamma")

    # Partial update via PATCH
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "brand_color": "#10B981",
            "text_color": "#000000",
            "position": "BOTTOM_LEFT",
            "avatar_url": "https://example.com/bot-avatar.png",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["brand_color"] == "#10B981"
    assert data["text_color"] == "#000000"
    assert data["position"] == "BOTTOM_LEFT"
    assert data["avatar_url"] == "https://example.com/bot-avatar.png"
    # Identity untouched
    assert data["name"] == "Fussion Assistant"


@pytest.mark.asyncio
async def test_update_assistant_behavior(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst4@example.com", "Alice Asst4")
    project_id = await create_project(client, token, org_id, "Storefront Delta", "storefront-delta")

    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "is_enabled": False,
            "system_instructions": "Always respond politely and emphasize our sustainable sourcing.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_enabled"] is False
    assert data["system_instructions"] == "Always respond politely and emphasize our sustainable sourcing."


@pytest.mark.asyncio
async def test_validation_hex_color(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst5@example.com", "Alice Asst5")
    project_id = await create_project(client, token, org_id, "Storefront Epsilon", "storefront-epsilon")

    invalid_colors = ["red", "#123", "#1234567", "123456", "#gggggg", ""]
    for color in invalid_colors:
        resp = await client.patch(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
            headers={"Authorization": f"Bearer {token}"},
            json={"brand_color": color},
        )
        assert resp.status_code == 422, f"Expected 422 for invalid color: {color}"


@pytest.mark.asyncio
async def test_validation_avatar_url_and_strings(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst6@example.com", "Alice Asst6")
    project_id = await create_project(client, token, org_id, "Storefront Zeta", "storefront-zeta")

    # Reject non-http/https URLs
    bad_urls = ["javascript:alert(1)", "data:text/html;base64,abc", "ftp://files.com/a.png", "relative/path.png"]
    for url in bad_urls:
        resp = await client.patch(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
            headers={"Authorization": f"Bearer {token}"},
            json={"avatar_url": url},
        )
        assert resp.status_code == 422, f"Expected 422 for bad url: {url}"

    # Reject empty name
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "   "},
    )
    assert resp.status_code == 422

    # Reject oversized name (> 100 chars)
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "A" * 101},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reset_assistant_to_defaults(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst7@example.com", "Alice Asst7")
    project_id = await create_project(client, token, org_id, "Storefront Eta", "storefront-eta")

    # Customize assistant
    await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Custom Assistant",
            "brand_color": "#EF4444",
            "welcome_message": "Custom greeting",
            "position": "BOTTOM_LEFT",
            "is_enabled": False,
        },
    )

    # Reset via DELETE
    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Fussion Assistant"
    assert data["brand_color"] == "#6366F1"
    assert data["welcome_message"] == "Hi! How can I help you today?"
    assert data["position"] == "BOTTOM_RIGHT"
    assert data["is_enabled"] is True

    # Test explicit POST /reset endpoint as well
    resp2 = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant/reset",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "Fussion Assistant"


@pytest.mark.asyncio
async def test_assistant_preview_endpoint(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "alice_asst8@example.com", "Alice Asst8")
    project_id = await create_project(client, token, org_id, "Storefront Theta", "storefront-theta")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "assistant" in data
    assert data["assistant"]["name"] == "Fussion Assistant"
    assert "knowledge_base" in data
    assert "documents_count" in data["knowledge_base"]
    assert "mock_preview" in data
    assert "sample_user_message" in data["mock_preview"]
    assert "sample_assistant_response" in data["mock_preview"]
    assert "grounding_status" in data["mock_preview"]


@pytest.mark.asyncio
async def test_multi_tenant_isolation(client: AsyncClient) -> None:
    token_a, _, org_id_a = await register_user(client, "tenant_a@example.com", "Tenant A")
    token_b, _, _org_id_b = await register_user(client, "tenant_b@example.com", "Tenant B")

    proj_a = await create_project(client, token_a, org_id_a, "Project A", "proj-a")

    # Tenant B tries to GET Tenant A's assistant -> 404 (anti-enumeration)
    resp = await client.get(
        f"/api/v1/organizations/{org_id_a}/projects/{proj_a}/assistant",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404

    # Tenant B tries to PATCH Tenant A's assistant -> 404
    resp = await client.patch(
        f"/api/v1/organizations/{org_id_a}/projects/{proj_a}/assistant",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Hacked Bot"},
    )
    assert resp.status_code == 404

    # Tenant B tries to DELETE Tenant A's assistant -> 404
    resp = await client.delete(
        f"/api/v1/organizations/{org_id_a}/projects/{proj_a}/assistant",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multi_project_isolation(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "multi_proj@example.com", "Multi Proj")
    proj_1 = await create_project(client, token, org_id, "Project One", "proj-one")
    proj_2 = await create_project(client, token, org_id, "Project Two", "proj-two")

    # Create assistant in Project 1
    await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{proj_1}/assistant",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Project 1 Assistant"},
    )

    # Ensure Project 2 has its own isolated assistant
    resp2 = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_2}/assistant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "Fussion Assistant"  # Default, not Project 1's custom name


@pytest.mark.asyncio
async def test_rbac_permissions(client: AsyncClient) -> None:
    owner_token, _, org_id = await register_user(client, "rbac_owner@example.com", "RBAC Owner")
    project_id = await create_project(client, owner_token, org_id, "RBAC Project", "rbac-project")

    # Register a second user to invite as VIEWER
    viewer_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rbac_viewer@example.com",
            "password": "Password123!",
            "full_name": "RBAC Viewer",
            "org_name": "Viewer Solo Org",
        },
    )
    viewer_token = viewer_resp.json()["access_token"]
    viewer_email = viewer_resp.json()["user"]["email"]

    # Invite viewer into owner's org with VIEWER role
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": viewer_email, "role": "VIEWER"},
    )
    assert invite_resp.status_code == 201

    # VIEWER can GET assistant
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200

    # VIEWER can GET preview
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant/preview",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200

    # VIEWER CANNOT update assistant (403 Forbidden)
    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"name": "Viewer Bot"},
    )
    assert resp.status_code == 403

    # VIEWER CANNOT reset assistant (403 Forbidden)
    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403

    # Register and invite MEMBER
    member_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rbac_member@example.com",
            "password": "Password123!",
            "full_name": "RBAC Member",
            "org_name": "Member Solo Org",
        },
    )
    member_token = member_resp.json()["access_token"]
    member_email = member_resp.json()["user"]["email"]

    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": member_email, "role": "MEMBER"},
    )

    # MEMBER can read. Assistant configuration carries the tenant's grounding contract —
    # it decides what every guest is told — so it is owner/admin only
    # (standards-alignment.md G3 remediation).
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200

    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"name": "Member Updated Bot"},
    )
    assert resp.status_code == 403

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403

    # Register and invite ADMIN
    admin_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rbac_admin@example.com",
            "password": "Password123!",
            "full_name": "RBAC Admin",
            "org_name": "Admin Solo Org",
        },
    )
    admin_token = admin_resp.json()["access_token"]
    admin_email = admin_resp.json()["user"]["email"]

    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": admin_email, "role": "ADMIN"},
    )

    # ADMIN CAN read, update, and reset
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    resp = await client.patch(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Admin Updated Bot"},
    )
    assert resp.status_code == 200

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unique_project_assistant_constraint(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "unique_asst@example.com", "Unique User")
    project_id = await create_project(client, token, org_id, "Unique Project", "unique-project")

    # Access endpoint to auto-create assistant
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Attempting to insert a duplicate assistant row directly violates unique constraint
    from sqlalchemy.exc import IntegrityError
    session_factory = get_session_factory()
    async with session_factory() as db:
        dup = Assistant(
            project_id=uuid.UUID(project_id),
            name="Duplicate Assistant",
            welcome_message="Hi!",
            brand_color="#6366F1",
            text_color="#FFFFFF",
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_cascade_deletion(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "cascade_asst@example.com", "Cascade User")
    project_id = await create_project(client, token, org_id, "Cascade Project", "cascade-project")

    # Initialize assistant
    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/assistant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    asst_id = uuid.UUID(resp.json()["id"])

    # Verify assistant exists in DB
    session_factory = get_session_factory()
    async with session_factory() as db:
        asst = (await db.execute(select(Assistant).where(Assistant.id == asst_id))).scalar_one_or_none()
        assert asst is not None

        # Delete project directly via DB
        proj = (await db.execute(select(Project).where(Project.id == uuid.UUID(project_id)))).scalar_one()
        await db.delete(proj)
        await db.commit()

        # Verify assistant is cascade deleted
        asst_after = (await db.execute(select(Assistant).where(Assistant.id == asst_id))).scalar_one_or_none()
        assert asst_after is None
