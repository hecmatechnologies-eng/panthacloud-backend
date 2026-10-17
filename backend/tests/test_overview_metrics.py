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
    channel: Channel = Channel.EMAIL,
) -> None:
    """Create ``count`` answered conversations, then commit once.

    One commit for the whole scenario rather than one per conversation. Committing each one made
    this file take eleven minutes on its own, which is not a price worth paying for a definitions
    test - and nothing here is asserting on intermediate commits.
    """
    for _ in range(count):
        session = VisitorSession(
            project_id=project.id,
            channel=channel,
            # Unique per session: the index that stops one guest appearing twice is the same index
            # that makes a shared value a collision.
            external_id=f"{uuid.uuid4().hex}",
            created_at=asked_at,
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

    async def test_days_met_goal_scores_against_the_requested_goal(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """A tighter goal must be scored harder, or the setting on the page does nothing.

        This caught the endpoint comparing every day against the built-in 12 minutes while echoing
        back whatever goal was asked for. The page then showed "8 of 14 days · goal 5 min" where the
        8 was measured against 12 - a figure no setting could reproduce.
        """
        project = await make_project(db_session, client, org)
        asked = datetime.now(UTC) - timedelta(hours=3)
        # Every day averages 10 minutes.
        await seed(db_session, project, 25, asked_at=asked, waited_seconds=600)

        org_id, token = org
        loose = await client.get(
            f"{BASE}/{org_id}/overview-metrics?goal_minutes=12",
            headers={"Authorization": f"Bearer {token}"},
        )
        tight = await client.get(
            f"{BASE}/{org_id}/overview-metrics?goal_minutes=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert loose.status_code == 200, loose.text
        assert tight.status_code == 200, tight.text
        # 10 minutes passes a 12-minute goal and fails a 5-minute one.
        assert loose.json()["totals"]["days_met_goal"] >= 1
        assert tight.json()["totals"]["days_met_goal"] == 0
        assert tight.json()["goal_minutes"] == 5


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


class TestWindow:
    async def test_the_window_is_as_wide_as_the_page_says(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """`days` has to mean days on the chart, not hours before now.

        Measuring back `days * 24` hours from the current instant spans both endpoints inclusively,
        so a 14-day window returned 15 daily points under a caption reading "the last 14 days". A
        chart with one more day on it than the sentence promises is a small lie, and it is the kind
        a hotel notices before they trust the rest.
        """
        project = await make_project(db_session, client, org)
        asked = datetime.now(UTC) - timedelta(hours=6)
        await seed(db_session, project, 25, asked_at=asked)
        body = await fetch(client, org)
        assert body["range_days"] == 14
        assert len(body["daily"]) <= body["range_days"]
        assert body["totals"]["days_in_window"] <= body["range_days"]

    async def test_the_window_still_includes_today(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """Tightening the window must not cut off the current day, which is usually the one being
        looked at."""
        project = await make_project(db_session, client, org)
        await seed(db_session, project, 25, asked_at=datetime.now(UTC) - timedelta(hours=2))
        body = await fetch(client, org)
        assert body["daily"][-1]["date"] == datetime.now(UTC).date().isoformat()


class TestWeekly:
    """The weekly series is what the trend panel draws, and it is built separately from the daily
    one. Built separately means it can be wrong on its own - and it was: message volume was the
    literal 0 and wait time was the literal None, which drew an empty second chart while the
    numbers still looked like a successful response."""

    async def test_weekly_carries_messages_and_wait(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        project = await make_project(db_session, client, org)
        await seed(
            db_session, project, 30, asked_at=datetime.now(UTC) - timedelta(days=2), waited_seconds=600
        )
        week = (await fetch(client, org))["weekly"][-1]
        assert week["guest_messages"] == 30
        assert week["average_wait_minutes"] == 10.0

    async def test_weekly_sums_older_days_not_just_the_display_window(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """The daily panel shows 14 days; the weekly panel covers weeks. A week that ends outside
        the daily window still has to carry its own volume, or the trend chart understates every
        week but the last."""
        project = await make_project(db_session, client, org)
        await seed(
            db_session, project, 25, asked_at=datetime.now(UTC) - timedelta(days=40), waited_seconds=600
        )
        weekly = (await fetch(client, org))["weekly"]
        assert sum(w["guest_messages"] for w in weekly) == 25

    async def test_weekly_mean_weights_busy_days_heavier(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """A quiet day and a busy day, in the same week, with different waits.

        Ten slow answers and one fast one is a mean of roughly nine minutes, not the five and a half
        an unweighted average of the two daily figures would report.
        """
        project = await make_project(db_session, client, org)
        now = datetime.now(UTC)
        monday = now - timedelta(days=now.weekday())
        await seed(db_session, project, 10, asked_at=monday + timedelta(days=1), waited_seconds=600)
        await seed(db_session, project, 1, asked_at=monday + timedelta(days=2), waited_seconds=120)
        week = (await fetch(client, org))["weekly"][-1]
        # (10 * 600 + 1 * 120) / 11 = 556 seconds = 9.27 minutes.
        assert week["average_wait_minutes"] == 9.3

    async def test_a_week_with_no_answers_reports_null_not_zero(
        self, client: AsyncClient, db_session: AsyncSession, org
    ) -> None:
        """Same reason as the daily case, and the same trap: zero would be read as instant."""
        project = await make_project(db_session, client, org)
        await seed(
            db_session,
            project,
            5,
            asked_at=datetime.now(UTC) - timedelta(days=2),
            waited_seconds=None,
            status=ConversationStatus.ESCALATED,
        )
        week = (await fetch(client, org))["weekly"][-1]
        assert week["average_wait_minutes"] is None


class TestChannels:
    """Where guests arrive. Counted per session, not per conversation, and reported whatever
    channels exist rather than a fixed three - the platform supports more than the three we were
    asked about, and a fixed list makes the remainder silently disappear."""

    async def test_counts_sessions_by_channel(self, client: AsyncClient, db_session, org) -> None:
        project = await make_project(db_session, client, org)
        now = datetime.now(UTC)
        await seed(db_session, project, 3, asked_at=now - timedelta(hours=1), channel=Channel.EMAIL)
        await seed(db_session, project, 2, asked_at=now - timedelta(hours=1), channel=Channel.WEB)
        body = await fetch(client, org)
        today = body["channel_daily"][-1]["sessions"]
        assert today.get("email") == 3
        assert today.get("web") == 2
        assert set(body["channels"]) == {"email", "web"}

    async def test_a_day_with_no_traffic_is_present_and_zero(
        self, client: AsyncClient, db_session, org
    ) -> None:
        """A gap day has to appear as an explicit zero. Missing entirely, a chart draws a straight
        line through a day where nothing happened, which reads as "steady" rather than "closed"."""
        project = await make_project(db_session, client, org)
        await seed(
            db_session,
            project,
            5,
            asked_at=datetime.now(UTC) - timedelta(days=3),
            channel=Channel.WHATSAPP,
        )
        body = await fetch(client, org)
        assert len(body["channel_daily"]) == body["range_days"]
        assert body["channel_daily"][-1]["sessions"] == {}

    async def test_channel_traffic_needs_no_answered_conversations(
        self, client: AsyncClient, db_session, org
    ) -> None:
        """Traffic is traffic. A hotel can know where its guests arrive long before it can say how
        quickly they were answered, and hiding the one chart that still works would be a shame."""
        project = await make_project(db_session, client, org)
        await seed(db_session, project, 4, asked_at=datetime.now(UTC) - timedelta(hours=1))
        body = await fetch(client, org)
        assert body["insufficient_data"] is True
        assert any(day["sessions"] for day in body["channel_daily"])

    async def test_channel_order_is_stable_not_query_order(
        self, client: AsyncClient, db_session, org
    ) -> None:
        """The chart colours a channel by its position in this list.

        Taking the order straight from grouped rows makes a channel change colour whenever the
        database's plan changes, so the reader has to re-learn the chart on every load. Inserted in
        reverse canonical order here to prove the endpoint imposes its own.
        """
        project = await make_project(db_session, client, org)
        asked = datetime.now(UTC) - timedelta(hours=1)
        for channel in (Channel.SMS, Channel.TELEGRAM, Channel.EMAIL, Channel.WHATSAPP, Channel.WEB):
            await seed(db_session, project, 2, asked_at=asked, channel=channel)
        body = await fetch(client, org)
        assert body["channels"] == ["web", "whatsapp", "email", "telegram", "sms"]

    async def test_channels_are_scoped_to_the_tenant(self, client: AsyncClient, db_session, org) -> None:
        project = await make_project(db_session, client, org)
        await seed(
            db_session, project, 9, asked_at=datetime.now(UTC) - timedelta(hours=1), channel=Channel.EMAIL
        )
        other_org = await make_org(client)
        other = await fetch(client, other_org)
        assert other["channels"] == []
        assert all(not day["sessions"] for day in other["channel_daily"])


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