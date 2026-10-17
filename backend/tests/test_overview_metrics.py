"""Overview metrics: the definitions, and the cases where they must refuse to answer.

Every number on that dashboard is arguable. The moment a hotel sees "average wait 10 minutes", the
only defence is being able to reproduce the figure and say exactly what was counted - so the
interesting tests are the boundaries, not the happy path.

**The one that matters most** is ``test_an_unanswered_conversation_does_not_count_as_zero_wait``.
Counting a conversation nobody replied to as zero would make the average *improve* as service got
worse. A metric that moves the wrong way is worse than none, because it is believed.

Run against Postgres too, not just SQLite. ``TEST_DATABASE_URL`` selects the engine; this file
writes raw SQL and that is exactly where a dialect difference hides.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    Channel,
    Conversation,
    ConversationIntent,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageRole,
    VisitorSession,
)
from app.models.project import Project

BASE = "/api/v1/organizations"


async def make_org(client: AsyncClient) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ov-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"Overview {suffix}",
            "org_name": f"Overview Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    org_id = (
        await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    ).json()[0]["id"]
    return org_id, token


@pytest.fixture
async def org(client: AsyncClient) -> tuple[str, str]:
    return await make_org(client)


async def make_project(db: AsyncSession, client: AsyncClient, org: tuple[str, str]) -> Project:
    org_id, token = org
    proj = await client.post(
        f"{BASE}/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "K Hotels", "slug": f"ov-{uuid.uuid4().hex[:8]}"},
    )
    assert proj.status_code == 201, proj.text
    return await db.get(Project, uuid.UUID(proj.json()["id"]))


async def seed(
    db: AsyncSession,
    project: Project,
    count: int,
    *,
    asked_at: datetime,
    waited_seconds: int | None = 600,
    status: ConversationStatus = ConversationStatus.ANSWERED,
    intent: ConversationIntent = ConversationIntent.INFORMATIONAL,
) -> None:
    """Create ``count`` answered conversations, then commit once.

    One commit for the whole scenario rather than one per conversation. Committing each one made
    this file take eleven minutes on its own, which is not a price worth paying for a definitions
    test - and nothing here is asserting on intermediate commits.
    """
    for _ in range(count):
        session = VisitorSession(
            project_id=project.id,
            channel=Channel.EMAIL,
            # Unique per session: the index that stops one guest appearing twice is the same index
            # that makes a shared value a collision.
            external_id=f"{uuid.uuid4().hex}",
            expires_at=asked_at + timedelta(days=30),
        )
        db.add(session)
        await db.flush()

        conversation = Conversation(
            session_id=session.id,
            retention_expires_at=asked_at + timedelta(days=365),
            status=status,
            intent=intent,
            created_at=asked_at,
        )
        db.add(conversation)
        await db.flush()

        db.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.VISITOR,
                direction=MessageDirection.INBOUND,
                content="What time is check-out?",
                created_at=asked_at,
            )
        )
        if waited_seconds is not None:
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    direction=MessageDirection.OUTBOUND,
                    content="Check-out is by 11:00.",
                    created_at=asked_at + timedelta(seconds=waited_seconds),
                )
            )
    await db.commit()


async def fetch(client: AsyncClient, org: tuple[str, str]) -> dict:
    org_id, token = org
    response = await client.get(
        f"{BASE}/{org_id}/overview-metrics", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestWithheld:
    async def test_too_little_traffic_says_so(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """Three enquiries produce a mean and a rate. A chart through them is decoration."""
        project = await make_project(db_session, client, org)
        await seed(db_session, project, 3, asked_at=datetime.now(UTC) - timedelta(hours=1))
        assert (await fetch(client, org))["insufficient_data"] is True

    async def test_enough_traffic_reports(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        project = await make_project(db_session, client, org)
        await seed(db_session, project, 25, asked_at=datetime.now(UTC) - timedelta(hours=1))
        assert (await fetch(client, org))["insufficient_data"] is False

    async def test_no_projects_is_not_an_error(self, client: AsyncClient, org) -> None:
        """An empty tenant is a state to render, not a failure."""
        body = await fetch(client, org)
        assert body["insufficient_data"] is True
        assert body["totals"]["guest_messages"] == 0


class TestWaitTime:
    async def test_the_mean_is_over_answered_conversations(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        project = await make_project(db_session, client, org)
        await seed(db_session, project, 25, asked_at=datetime.now(UTC) - timedelta(hours=1))
        assert (await fetch(client, org))["totals"]["average_wait_minutes"] == 10.0

    async def test_an_unanswered_conversation_does_not_count_as_zero_wait(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """The important one.

        A guest who never got an answer waited an unbounded time. Counting that as zero makes the
        average fall as service gets worse.
        """
        project = await make_project(db_session, client, org)
        asked = datetime.now(UTC) - timedelta(hours=2)
        await seed(db_session, project, 20, asked_at=asked, waited_seconds=600)
        await seed(db_session, project, 20, asked_at=asked, waited_seconds=None)
        # Ten minutes, not thirty. The unanswered twenty are excluded, not counted as instant.
        assert (await fetch(client, org))["totals"]["average_wait_minutes"] == 10.0

    async def test_days_met_goal_never_exceeds_days_in_window(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        project = await make_project(db_session, client, org)
        asked = datetime.now(UTC) - timedelta(hours=3)
        await seed(db_session, project, 20, asked_at=asked, waited_seconds=600)
        await seed(db_session, project, 5, asked_at=asked, waited_seconds=1800)
        totals = (await fetch(client, org))["totals"]
        assert totals["days_met_goal"] <= totals["days_in_window"]


class TestSeriousEnquiries:
    async def test_escalation_and_complaint_both_count(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """Two routes to the same outcome, and neither replaces the other.

        A complaint can be handled and stay a complaint; an escalation can be raised by staff for
        anything at all. Counting only one misses half the cases a hotel would recognise.
        """
        project = await make_project(db_session, client, org)
        asked = datetime.now(UTC) - timedelta(hours=1)
        await seed(db_session, project, 18, asked_at=asked)
        await seed(
            db_session, project, 1, asked_at=asked, status=ConversationStatus.ESCALATED
        )
        await seed(
            db_session, project, 1, asked_at=asked, intent=ConversationIntent.COMPLAINT
        )
        # 2 serious out of 20 conversations.
        assert (await fetch(client, org))["totals"]["serious_per_100"] == 10.0


class TestTenancy:
    async def test_another_organisation_sees_nothing(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        project = await make_project(db_session, client, org)
        await seed(db_session, project, 30, asked_at=datetime.now(UTC) - timedelta(hours=1))

        # Not unpacked: make_org already returns the (org_id, token) pair that fetch expects.
        other_org = await make_org(client)
        assert (await fetch(client, other_org))["totals"]["guest_messages"] == 0

    async def test_anonymous_access_is_refused(self, client: AsyncClient, org) -> None:
        org_id, _ = org
        response = await client.get(f"{BASE}/{org_id}/overview-metrics")
        assert response.status_code in (401, 403)