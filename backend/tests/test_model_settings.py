"""Per-organization model selection (FR-072, FR-075).

The model is an economic setting: it decides what every conversation costs and how well it answers.
These tests pin who may change it, what may be chosen, and that one organization's choice is
invisible to another.

`settings` is patched rather than read from `.env`: the allow-list is deployment configuration, and
a test that inherits it fails for a reason unrelated to what it is testing.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_session_factory
from app.models.membership import RoleEnum
from app.models.organization_model_settings import OrganizationModelSettings

DEFAULT_MODEL = "model-default"
CHOSEN_MODEL = "model-strong"


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "MODEL_ID", DEFAULT_MODEL)
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [DEFAULT_MODEL, CHOSEN_MODEL])


async def _org(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    """Register a user and return ``(token, org_id)``."""
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


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _stored(org_id: str) -> list[str]:
    session_factory = get_session_factory()
    async with session_factory() as db:
        return list(
            (
                await db.execute(
                    select(OrganizationModelSettings.model_id).where(
                        OrganizationModelSettings.organization_id == uuid.UUID(org_id)
                    )
                )
            )
            .scalars()
            .all()
        )


# ============================================================
# 1. The default, and choosing otherwise
# ============================================================


@pytest.mark.asyncio
async def test_an_organization_without_a_choice_gets_the_deployment_default(
    client: AsyncClient, models: None
) -> None:
    token, org_id = await _org(client, "ms_default@example.com", "MsDefault")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/model-settings", headers=_hdr(token)
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == DEFAULT_MODEL
    assert body["is_override"] is False
    assert body["default_model_id"] == DEFAULT_MODEL
    assert body["allowed_model_ids"] == [DEFAULT_MODEL, CHOSEN_MODEL]
    assert await _stored(org_id) == []


@pytest.mark.asyncio
async def test_choosing_a_model_is_reflected_and_marked_as_an_override(
    client: AsyncClient, models: None
) -> None:
    token, org_id = await _org(client, "ms_choose@example.com", "MsChoose")

    put = await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": CHOSEN_MODEL},
    )
    assert put.status_code == 200, put.text
    assert put.json()["model_id"] == CHOSEN_MODEL
    assert put.json()["is_override"] is True

    assert await _stored(org_id) == [CHOSEN_MODEL]


@pytest.mark.asyncio
async def test_clearing_the_choice_returns_to_the_deployment_default(
    client: AsyncClient, models: None
) -> None:
    token, org_id = await _org(client, "ms_clear@example.com", "MsClear")
    await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": CHOSEN_MODEL},
    )

    cleared = await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": None},
    )

    assert cleared.status_code == 200
    assert cleared.json()["model_id"] == DEFAULT_MODEL
    assert cleared.json()["is_override"] is False
    # Cleared means gone, not stored-as-the-default: otherwise the default could never change.
    assert await _stored(org_id) == []


# ============================================================
# 2. What may be chosen
# ============================================================


@pytest.mark.asyncio
async def test_a_model_outside_the_allow_list_is_refused_with_the_permitted_values(
    client: AsyncClient, models: None
) -> None:
    token, org_id = await _org(client, "ms_disallowed@example.com", "MsDisallowed")

    resp = await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": "gpt-4o"},
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "gpt-4o" in detail
    # The refusal has to say what *is* permitted, or it is only a scolding.
    assert CHOSEN_MODEL in detail
    assert await _stored(org_id) == []


@pytest.mark.asyncio
async def test_blank_input_clears_rather_than_storing_an_empty_model(
    client: AsyncClient, models: None
) -> None:
    token, org_id = await _org(client, "ms_blank@example.com", "MsBlank")

    resp = await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": "   "},
    )

    assert resp.status_code == 200
    assert resp.json()["is_override"] is False
    assert await _stored(org_id) == []


# ============================================================
# 3. Tenancy
# ============================================================


@pytest.mark.asyncio
async def test_one_organizations_choice_does_not_affect_another(
    client: AsyncClient, models: None
) -> None:
    token_a, org_a = await _org(client, "ms_a@example.com", "MsA")
    token_b, org_b = await _org(client, "ms_b@example.com", "MsB")

    await client.put(
        f"/api/v1/organizations/{org_a}/model-settings",
        headers=_hdr(token_a),
        json={"model_id": CHOSEN_MODEL},
    )

    other = await client.get(
        f"/api/v1/organizations/{org_b}/model-settings", headers=_hdr(token_b)
    )
    assert other.json()["model_id"] == DEFAULT_MODEL
    assert await _stored(org_b) == []


# ============================================================
# 4. Who may change it
# ============================================================


@pytest.mark.asyncio
async def test_a_viewer_may_read_the_model_but_not_change_it(
    client: AsyncClient, models: None
) -> None:
    owner_token, org_id = await _org(client, "ms_owner@example.com", "MsOwner")
    viewer_token, _ = await _org(client, "ms_viewer@example.com", "MsViewer")
    invited = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=_hdr(owner_token),
        json={"email": "ms_viewer@example.com", "role": RoleEnum.VIEWER.value},
    )
    assert invited.status_code == 201, invited.text

    read = await client.get(
        f"/api/v1/organizations/{org_id}/model-settings", headers=_hdr(viewer_token)
    )
    write = await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(viewer_token),
        json={"model_id": CHOSEN_MODEL},
    )

    assert read.status_code == 200
    assert write.status_code == 403
    assert await _stored(org_id) == []


@pytest.mark.asyncio
async def test_a_member_may_not_change_it_either(client: AsyncClient, models: None) -> None:
    """Running an integration and setting the bill for everyone are different authorities."""
    owner_token, org_id = await _org(client, "ms_owner2@example.com", "MsOwner2")
    member_token, _ = await _org(client, "ms_member@example.com", "MsMember")
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=_hdr(owner_token),
        json={"email": "ms_member@example.com", "role": RoleEnum.MEMBER.value},
    )

    resp = await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(member_token),
        json={"model_id": CHOSEN_MODEL},
    )

    assert resp.status_code == 403


# ============================================================
# 5. Lifecycle
# ============================================================


@pytest.mark.asyncio
async def test_deleting_the_organization_removes_its_choice(
    client: AsyncClient, models: None
) -> None:
    """The ORM cascade, not the FK clause: SQLite runs with foreign keys unenforced.

    Driven through the ORM rather than the API because there is no `DELETE /organizations` endpoint
    yet — the permission exists, the route does not.
    """
    from app.models.organization import Organization

    token, org_id = await _org(client, "ms_cascade@example.com", "MsCascade")
    await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": CHOSEN_MODEL},
    )
    assert await _stored(org_id) == [CHOSEN_MODEL]

    session_factory = get_session_factory()
    async with session_factory() as db:
        organization = (
            await db.execute(
                select(Organization).where(Organization.id == uuid.UUID(org_id))
            )
        ).scalar_one()
        await db.delete(organization)
        await db.commit()

    assert await _stored(org_id) == []


# ============================================================
# 6. The change is audited
# ============================================================


@pytest.mark.asyncio
async def test_changing_the_model_is_audited(client: AsyncClient, models: None) -> None:
    """Organization-level changes are auditable now that `project_id` is optional.

    Before, `audit_events.project_id` was NOT NULL and pointed at a project, so a change with no
    project could not be recorded at all.
    """
    from app.models.audit_event import AuditEvent

    token, org_id = await _org(client, "ms_audit@example.com", "MsAudit")
    await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": CHOSEN_MODEL},
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        events = (
            await db.execute(
                select(AuditEvent).where(AuditEvent.organization_id == uuid.UUID(org_id))
            )
        ).scalars().all()

    assert [event.event_type for event in events] == ["organization.model.changed"]
    assert events[0].project_id is None
    assert events[0].resource_type == "organization"
    assert events[0].payload["model_id"] == CHOSEN_MODEL


@pytest.mark.asyncio
async def test_a_refused_change_is_not_audited(client: AsyncClient, models: None) -> None:
    """The audit trail records what happened, not what was attempted."""
    from app.models.audit_event import AuditEvent

    token, org_id = await _org(client, "ms_noaudit@example.com", "MsNoAudit")
    await client.put(
        f"/api/v1/organizations/{org_id}/model-settings",
        headers=_hdr(token),
        json={"model_id": "gpt-4o"},
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        events = (
            await db.execute(
                select(AuditEvent).where(AuditEvent.organization_id == uuid.UUID(org_id))
            )
        ).scalars().all()

    assert events == []
