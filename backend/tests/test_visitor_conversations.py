"""Step B · B3 — visitor session / conversation / message schema (FR-056, FR-119–121).

Schema only: nothing in the application writes these tables yet (B4 is the first endpoint). These
tests create rows through the ORM directly and assert the shape B4 will depend on — the tenancy
path, the retention fields, ordering, and the cascade that is the deletion path for FR-119/120.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.database import get_session_factory
from app.models.conversation import Conversation, Message, MessageRole, VisitorSession
from app.models.website_integration import WebsiteIntegration

# ============================================================
# Fixtures / helpers
# ============================================================


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
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
    token = resp.json()["access_token"]
    orgs = await client.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return token, orgs.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_integration(
    client: AsyncClient, token: str, org_id: str, proj_id: str
) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    assert resp.status_code == 201
    return resp.json()


async def seed_session(
    integration_id: str,
    origin: str = "https://shop.example.com",
    session_ttl: timedelta = timedelta(hours=1),
) -> uuid.UUID:
    session_factory = get_session_factory()
    async with session_factory() as db:
        session = VisitorSession(
            integration_id=uuid.UUID(integration_id),
            origin=origin,
            expires_at=datetime.now(UTC) + session_ttl,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session.id


async def seed_conversation(
    session_id: uuid.UUID, retention: timedelta = timedelta(days=30)
) -> uuid.UUID:
    session_factory = get_session_factory()
    async with session_factory() as db:
        conversation = Conversation(
            session_id=session_id,
            retention_expires_at=datetime.now(UTC) + retention,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation.id


async def seed_message(
    conversation_id: uuid.UUID,
    role: MessageRole,
    content: str,
    created_at: datetime | None = None,
) -> uuid.UUID:
    session_factory = get_session_factory()
    async with session_factory() as db:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        if created_at is not None:
            message.created_at = created_at
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message.id


async def row_counts() -> tuple[int, int, int]:
    session_factory = get_session_factory()
    async with session_factory() as db:
        return (
            (await db.execute(select(func.count()).select_from(VisitorSession))).scalar_one(),
            (await db.execute(select(func.count()).select_from(Conversation))).scalar_one(),
            (await db.execute(select(func.count()).select_from(Message))).scalar_one(),
        )


async def tenant_fixture(
    client: AsyncClient, email: str, name: str
) -> tuple[dict, str, str]:
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    return integration, org_id, proj_id


def integration_url(org_id: str, proj_id: str) -> str:
    return f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"


# ============================================================
# 1. Shape and tenancy path
# ============================================================


@pytest.mark.asyncio
async def test_round_trip_and_tenancy_path(client: AsyncClient) -> None:
    integration, org_id, proj_id = await tenant_fixture(
        client, "vc_owner@example.com", "VcOwner"
    )
    session_id = await seed_session(integration["id"])
    conversation_id = await seed_conversation(session_id)
    await seed_message(conversation_id, MessageRole.VISITOR, "Do you deliver?")
    await seed_message(conversation_id, MessageRole.ASSISTANT, "Yes, within town.")

    session_factory = get_session_factory()
    async with session_factory() as db:
        session = (
            await db.execute(
                select(VisitorSession)
                .options(
                    selectinload(VisitorSession.conversations).selectinload(Conversation.messages),
                    selectinload(VisitorSession.integration).selectinload(
                        WebsiteIntegration.project
                    ),
                )
                .where(VisitorSession.id == session_id)
            )
        ).scalar_one()

        # Tenancy is the path integration → project → organization; no org column to drift.
        assert session.integration.id == uuid.UUID(integration["id"])
        assert session.integration.project_id == uuid.UUID(proj_id)
        assert session.integration.project.organization_id == uuid.UUID(org_id)

        assert session.origin == "https://shop.example.com"
        assert session.expires_at > session.created_at
        conversation = session.conversations[0]
        assert conversation.id == conversation_id
        assert conversation.retention_expires_at > conversation.created_at
        assert [m.role for m in conversation.messages] == [
            MessageRole.VISITOR,
            MessageRole.ASSISTANT,
        ]


@pytest.mark.asyncio
async def test_messages_are_ordered_by_created_at(client: AsyncClient) -> None:
    integration, _, _ = await tenant_fixture(client, "vc_order@example.com", "VcOrder")
    session_id = await seed_session(integration["id"])
    conversation_id = await seed_conversation(session_id)

    base = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    # Inserted out of order on purpose.
    await seed_message(conversation_id, MessageRole.ASSISTANT, "third", base + timedelta(seconds=2))
    await seed_message(conversation_id, MessageRole.VISITOR, "first", base)
    await seed_message(conversation_id, MessageRole.ASSISTANT, "second", base + timedelta(seconds=1))

    session_factory = get_session_factory()
    async with session_factory() as db:
        conversation = (
            await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conversation_id)
            )
        ).scalar_one()
        assert [m.content for m in conversation.messages] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_message_role_enum_values() -> None:
    assert {role.value for role in MessageRole} == {"VISITOR", "ASSISTANT"}


@pytest.mark.asyncio
async def test_messages_with_equal_timestamps_have_a_total_order(client: AsyncClient) -> None:
    """created_at alone is not a total order; two turns in one tick must still read back stably."""
    integration, _, _ = await tenant_fixture(client, "vc_tie@example.com", "VcTie")
    session_id = await seed_session(integration["id"])
    conversation_id = await seed_conversation(session_id)

    same_instant = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    id_a = await seed_message(conversation_id, MessageRole.VISITOR, "a", same_instant)
    id_b = await seed_message(conversation_id, MessageRole.ASSISTANT, "b", same_instant)

    session_factory = get_session_factory()
    async with session_factory() as db:
        conversation = (
            await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conversation_id)
            )
        ).scalar_one()
        assert [m.id for m in conversation.messages] == sorted([id_a, id_b])


# ============================================================
# 2. Retention fields are required
# ============================================================


@pytest.mark.asyncio
async def test_session_expiry_is_required(client: AsyncClient) -> None:
    integration, _, _ = await tenant_fixture(client, "vc_req@example.com", "VcReq")
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            VisitorSession(
                integration_id=uuid.UUID(integration["id"]),
                origin="https://shop.example.com",
                # expires_at deliberately omitted: the retention field must not be optional.
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


@pytest.mark.asyncio
async def test_conversation_retention_is_required(client: AsyncClient) -> None:
    integration, _, _ = await tenant_fixture(client, "vc_ret@example.com", "VcRet")
    session_id = await seed_session(integration["id"])
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(Conversation(session_id=session_id))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


# ============================================================
# 3. Cascade — the deletion path (FR-119/FR-120)
# ============================================================


@pytest.mark.asyncio
async def test_deleting_integration_cascades_to_messages(client: AsyncClient) -> None:
    token, org_id = await register_user(client, "vc_casc@example.com", "VcCasc")
    proj_id = await create_project(client, token, org_id, "VcCasc Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    session_id = await seed_session(integration["id"])
    conversation_id = await seed_conversation(session_id)
    await seed_message(conversation_id, MessageRole.VISITOR, "hello")

    assert await row_counts() == (1, 1, 1)

    resp = await client.delete(
        integration_url(org_id, proj_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    assert await row_counts() == (0, 0, 0)


@pytest.mark.asyncio
async def test_deleting_project_cascades_to_messages(client: AsyncClient) -> None:
    token, org_id = await register_user(client, "vc_proj@example.com", "VcProj")
    proj_id = await create_project(client, token, org_id, "VcProj Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    session_id = await seed_session(integration["id"])
    conversation_id = await seed_conversation(session_id)
    await seed_message(conversation_id, MessageRole.ASSISTANT, "hi")

    resp = await client.delete(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    assert await row_counts() == (0, 0, 0)


@pytest.mark.asyncio
async def test_deleting_conversation_removes_messages_but_not_session(
    client: AsyncClient,
) -> None:
    integration, _, _ = await tenant_fixture(client, "vc_conv@example.com", "VcConv")
    session_id = await seed_session(integration["id"])
    conversation_id = await seed_conversation(session_id)
    await seed_message(conversation_id, MessageRole.VISITOR, "hello")

    session_factory = get_session_factory()
    async with session_factory() as db:
        conversation = (
            await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        ).scalar_one()
        await db.delete(conversation)
        await db.commit()

    assert await row_counts() == (1, 0, 0)


@pytest.mark.asyncio
async def test_one_tenant_cascade_does_not_touch_another(client: AsyncClient) -> None:
    token_a, org_a = await register_user(client, "vc_iso_a@example.com", "VcIsoA")
    proj_a = await create_project(client, token_a, org_a, "VcIsoA Proj")
    integration_a = await create_integration(client, token_a, org_a, proj_a)

    integration_b, _, _ = await tenant_fixture(client, "vc_iso_b@example.com", "VcIsoB")

    session_a = await seed_session(integration_a["id"], origin="https://a.example.com")
    await seed_message(await seed_conversation(session_a), MessageRole.VISITOR, "a")
    session_b = await seed_session(integration_b["id"], origin="https://b.example.com")
    await seed_message(await seed_conversation(session_b), MessageRole.VISITOR, "b")

    assert await row_counts() == (2, 2, 2)

    resp = await client.delete(
        integration_url(org_a, proj_a),
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 204

    # B's session, conversation and message survive.
    assert await row_counts() == (1, 1, 1)
