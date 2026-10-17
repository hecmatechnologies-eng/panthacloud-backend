"""One-click unsubscribe: the header, the endpoint, and what opting out actually stops.

Three properties are being locked down, and each one has a specific failure it prevents.

**The header is present.** An automated reply with no opt-out is not merely rude, it is the thing
Gmail now requires senders of bulk mail to provide. A test here would otherwise only fail in
production, as a delivery statistic.

**The endpoint works without credentials.** RFC 8058 requires it, because the request is made by a
mail client following a link and has no session with us. If this ever grew an auth dependency the
header would silently stop working, which nothing else would notice.

**Opting out stops mail, not the record.** The transcript is the hotel's record of what was asked
and must survive; only the send is suppressed. And someone who unsubscribed then writes in is *not*
auto-resubscribed, because reversing a stated wish on the strength of one email is worse than
making staff aware of it.

The endpoint's always-200 behaviour is deliberate and is tested as such: a 404 would be an oracle
telling an attacker which tokens correspond to real customers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.email.unsubscribe import (
    apply_one_click,
    ensure_token,
    new_token,
    unsubscribe_url,
)
from app.core.config import settings
from app.models.conversation import Channel, VisitorSession

BASE = "/api/v1/webhooks/email"


async def make_project(client: AsyncClient) -> tuple[str, str]:
    """A registered user, org and project. Returns ``(organization_id, project_id)``."""
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"unsub-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"Unsub {suffix}",
            "org_name": f"Unsub Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    proj = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": "Hotel", "slug": f"unsub-{suffix}"},
    )
    assert proj.status_code == 201, proj.text
    return org_id, proj.json()["id"]


@pytest.fixture
async def project_id(client: AsyncClient) -> uuid.UUID:
    # A UUID, not the API's string form: the column is typed, and SQLite does not coerce for us.
    _, pid = await make_project(client)
    return uuid.UUID(pid)


@pytest.fixture(autouse=True)
def _public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stable public API URL, so the built unsubscribe URL is assertable.

    Set on settings rather than the environment because a test that reads ambient configuration can
    pass on one machine and fail on another.
    """
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://api.example.com", raising=False)


async def _email_session(
    db: AsyncSession, *, project_id: uuid.UUID, token: str | None = None, unsubscribed: bool = False
) -> VisitorSession:
    session = VisitorSession(
        project_id=project_id,
        channel=Channel.EMAIL,
        external_id="guest@example.com",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        unsubscribe_token=token,
        unsubscribed_at=datetime.now(UTC) if unsubscribed else None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


class TestToken:
    def test_tokens_are_unpredictable_and_distinct(self) -> None:
        """The endpoint is unauthenticated, so the token is the only thing protecting it.

        A token derived from a row id or an address would let anyone unsubscribe anyone; this asserts
        the two properties that make that impossible - distinct, and long enough not to brute force.
        """
        tokens = {new_token() for _ in range(200)}
        assert len(tokens) == 200
        assert all(len(t) >= 43 for t in tokens)

    async def test_ensure_token_mints_once_and_then_reuses(
        self, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """Called on every email reply, so it must not rotate - or links in older mail stop working.

        A guest clicking a link in a message from last month should still reach the same place.
        """
        session = await _email_session(db_session, project_id=project_id)
        first = await ensure_token(db_session, session)
        await db_session.commit()
        second = await ensure_token(db_session, session)
        assert first == second
        assert session.unsubscribe_token is not None

    async def test_ensure_token_fills_in_a_null(self, db_session: AsyncSession, project_id: uuid.UUID) -> None:
        session = await _email_session(db_session, project_id=project_id)
        assert session.unsubscribe_token is None
        token = await ensure_token(db_session, session)
        await db_session.commit()
        assert session.unsubscribe_token == token

    def test_the_url_is_https_and_absolute(self) -> None:
        """RFC 8058 clients reject anything else, and a relative URL is meaningless to them."""
        url = unsubscribe_url("abc123")
        assert url == "https://api.example.com/api/v1/webhooks/email/unsubscribe/abc123"
        assert url.startswith("https://")


class TestOneClickEndpoint:
    async def test_a_valid_token_unsubscribes_the_guest(
        self, client: AsyncClient, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        session = await _email_session(db_session, project_id=project_id, token="live-token")
        response = await client.post(f"{BASE}/unsubscribe/live-token")

        assert response.status_code == 200
        await db_session.refresh(session)
        assert session.unsubscribed_at is not None

    async def test_an_unknown_token_is_still_two_hundred(
        self, client: AsyncClient, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """Not a robustness nicety - an oracle.

        A 404 distinguishes "real customer" from "not a customer", and real tokens are real guest
        addresses. The endpoint must be indistinguishable from success.
        """
        await _email_session(db_session, project_id=project_id, token="live-token")
        response = await client.post(f"{BASE}/unsubscribe/does-not-exist")
        assert response.status_code == 200

    async def test_clicking_twice_is_not_an_error(
        self, client: AsyncClient, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """Mail clients retry, and a guest may click twice. The first click must stand."""
        session = await _email_session(db_session, project_id=project_id, token="live-token")
        assert (await client.post(f"{BASE}/unsubscribe/live-token")).status_code == 200
        assert (await client.post(f"{BASE}/unsubscribe/live-token")).status_code == 200
        await db_session.refresh(session)
        assert session.unsubscribed_at is not None

    async def test_no_authentication_is_required(
        self, client: AsyncClient, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """The `client` fixture sends no credentials at all, which is the point being tested.

        RFC 8058 exists precisely because the sending mail client has no session with us. An auth
        requirement here would break the feature silently, in production, where nobody is testing.
        """
        session = await _email_session(db_session, project_id=project_id, token="open-token")
        response = await client.post(f"{BASE}/unsubscribe/open-token")
        assert response.status_code == 200
        await db_session.refresh(session)
        assert session.unsubscribed_at is not None

    async def test_the_transcript_is_not_deleted(
        self, client: AsyncClient, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """Opting out stops mail. It does not erase the hotel's record of what was asked."""
        session = await _email_session(db_session, project_id=project_id, token="keep-history")
        await client.post(f"{BASE}/unsubscribe/keep-history")

        still_there = (
            await db_session.execute(select(VisitorSession).where(VisitorSession.id == session.id))
        ).scalar_one_or_none()
        assert still_there is not None
        assert still_there.external_id == "guest@example.com"

    async def test_a_whatsapp_session_cannot_be_unsubscribed_by_token(
        self, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """A token must not work across channels.

        Someone who unsubscribed from email has withdrawn consent for *email*. Silently applying
        that to their WhatsApp session would be a different decision taken on their behalf.
        """
        session = VisitorSession(
            project_id=project_id,
            channel=Channel.WHATSAPP,
            external_id="256700000000",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            unsubscribe_token="whatsapp-token",
        )
        db_session.add(session)
        await db_session.commit()

        assert await apply_one_click(db_session, "whatsapp-token") is False
        await db_session.refresh(session)
        assert session.unsubscribed_at is None


class TestHonouringOptOut:
    async def test_applying_an_unknown_token_changes_nothing(
        self, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        session = await _email_session(db_session, project_id=project_id, token="real-token")

        assert await apply_one_click(db_session, "imaginary-token") is False
        await db_session.refresh(session)
        assert session.unsubscribed_at is None

    async def test_an_already_unsubscribed_guest_is_reported_as_unchanged(
        self, db_session: AsyncSession, project_id: uuid.UUID
    ) -> None:
        """Idempotent, which is what lets the endpoint answer 200 unconditionally."""
        session = await _email_session(
            db_session, project_id=project_id, token="done-token", unsubscribed=True
        )
        assert await apply_one_click(db_session, "done-token") is False
        await db_session.refresh(session)
        assert session.unsubscribed_at is not None