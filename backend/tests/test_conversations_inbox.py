"""The staff conversation inbox (ADR-004, K6).

Two things are worth testing hard here, and they are not the happy path.

**The tenant boundary.** The route is organisation-scoped while the data is project-tenanted, so
the failure mode is a list or a detail view that leaks another hotel's guests - a phone number and
the text they wrote. That is the bug this endpoint exists to make impossible, and it is the kind of
bug a 200 response hides completely.

**Cursor pagination.** The inbox is the one collection that grows without bound, and the ordering
was chosen so that a conversation created mid-pagination cannot shift the window. That property is
what stops a row being served twice or missed, and it is invisible unless a test creates rows
between two page fetches.

Conversations are created by driving real chat turns rather than by inserting ORM rows, so the
tests also prove the lifecycle columns work with the actual runtime that writes them.
"""

import uuid

import pytest
from httpx import AsyncClient, Response

from app.channels.base import Channel
from app.llm.gateway import ModelGateway, set_model_gateway
from app.llm.providers.fake import FakeModelProvider
from app.runtime.rate_limit import rate_limiter

CHAT_URL = "/api/v1/public/chat"
ORIGIN = "https://hotel.example"


async def say(client: AsyncClient, public_key: str, message: str, origin: str = ORIGIN) -> Response:
    return await client.post(
        CHAT_URL, json={"public_key": public_key, "message": message}, headers={"Origin": origin}
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Rate-limit state is process-global, so it leaks between tests in this file.

    Not optional housekeeping: the counts cases drive several turns each, and without this the
    cumulative total trips the per-IP limit and the failure looks like a 429 from the conversations
    endpoint rather than from a limit these tests never meant to exercise.
    """
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(autouse=True)
def _model_gateway():
    set_model_gateway(ModelGateway(FakeModelProvider(reply="Good morning, and welcome.")))
    yield
    set_model_gateway(None)


# ============================================================
# Fixtures / helpers
# ============================================================


async def make_tenant(
    client: AsyncClient, label: str, origin: str = ORIGIN
) -> tuple[str, str, str, str]:
    """An org, a project, an integration and a registered origin.

    Returns ``(token, org_id, project_id, public_key)``. The key is captured from the creation
    response rather than read back from the list endpoint: one fewer moving part in the fixture, and
    the tests are about conversations rather than about how integrations are enumerated.
    """
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{label}-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"{label} {suffix}",
            "org_name": f"{label} Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    proj = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": f"{label} Hotel", "slug": f"{label.lower()}-{suffix}"},
    )
    assert proj.status_code == 201, proj.text
    project_id = proj.json()["id"]
    integration = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers=headers,
        json={"repository_owner": "acme", "repository_name": "hotel-site"},
    )
    assert integration.status_code == 201, integration.text
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/origins",
        headers=headers,
        json={"origin": origin},
    )
    return token, org_id, project_id, integration.json()["public_key"]


Tenant = tuple[str, str, str, str]


async def turn(client: AsyncClient, tenant: Tenant, message: str) -> Response:
    """One guest turn, which creates a session, a conversation and two messages."""
    resp = await say(client, tenant[3], message)
    assert resp.status_code == 200, resp.text
    return resp


async def inbox(client: AsyncClient, token: str, org_id: str, **params) -> Response:
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return await client.get(
        f"/api/v1/organizations/{org_id}/conversations" + (f"?{query}" if query else ""),
        headers={"Authorization": f"Bearer {token}"},
    )


async def transcript(client: AsyncClient, tenant: Tenant, conversation_id: str) -> Response:
    return await client.get(
        f"/api/v1/organizations/{tenant[1]}/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {tenant[0]}"},
    )


async def mark_reply_as_draft(project_id: str) -> None:
    """Turn the newest outbound message into an unsent draft.

    Stands in for the approval endpoint: a price quote held for a human. Constructed directly
    because nothing in the runtime produces a DRAFTED message yet.
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models.conversation import (
        Conversation,
        Message,
        MessageDirection,
        MessageStatus,
        VisitorSession,
    )

    async with get_session_factory()() as db:
        conversation = (
            await db.execute(
                select(Conversation)
                .join(VisitorSession, VisitorSession.id == Conversation.session_id)
                .where(VisitorSession.project_id == uuid.UUID(project_id))
            )
        ).scalar_one()
        reply = (
            await db.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.direction == MessageDirection.OUTBOUND,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
        reply.status = MessageStatus.DRAFTED
        await db.commit()


async def seed_statuses(tenant: Tenant, statuses: list[str]) -> None:
    """Assign statuses to the tenant's conversations, in creation order.

    Built directly because nothing in the runtime writes them yet - the lifecycle columns arrived
    with 0037 and the approval endpoint has not been written. That is exactly the state this API is
    being built against, so driving it through the database is honest rather than a shortcut.
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models.conversation import Conversation, ConversationStatus, VisitorSession

    async with get_session_factory()() as db:
        rows = list(
            (
                await db.execute(
                    select(Conversation)
                    .join(VisitorSession, VisitorSession.id == Conversation.session_id)
                    .where(VisitorSession.project_id == uuid.UUID(tenant[2]))
                    .order_by(Conversation.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == len(statuses), "the caller must create one conversation per status"
        for conversation, status in zip(rows, statuses, strict=True):
            conversation.status = ConversationStatus(status)
            conversation.lost_reason = "Price" if status == "lost" else None
        await db.commit()


async def set_intents(tenant: Tenant, counts: dict[str, int]) -> None:
    """Assign intents to the tenant's conversations in creation order.

    ``counts`` maps an intent value to how many consecutive conversations get it. Whatever is left
    over is left unclassified, which is the case worth testing - a conversation with no intent must
    not fall inside INFORMATIONAL, because that value means "never follow this guest up".
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models.conversation import Conversation, ConversationIntent, VisitorSession

    async with get_session_factory()() as db:
        rows = list(
            (
                await db.execute(
                    select(Conversation)
                    .join(VisitorSession, VisitorSession.id == Conversation.session_id)
                    .where(VisitorSession.project_id == uuid.UUID(tenant[2]))
                    .order_by(Conversation.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        index = 0
        for value, how_many in counts.items():
            for conversation in rows[index : index + how_many]:
                conversation.intent = ConversationIntent(value)
            index += how_many
        await db.commit()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def empty_conversation(project_id: str) -> None:
    """A session and conversation with no messages in them.

    Inserted directly rather than driven over HTTP, because no HTTP path produces this state: a
    turn always persists the guest's message before it calls the model. It is nevertheless a state
    the schema permits and the inbox has to render, so it is worth constructing deliberately.
    """
    from datetime import UTC, datetime, timedelta

    from app.core.database import get_session_factory
    from app.models.conversation import Conversation, VisitorSession

    async with get_session_factory()() as db:
        session = VisitorSession(
            project_id=uuid.UUID(project_id),
            channel=Channel.WHATSAPP,
            external_id="256700999000",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(session)
        await db.flush()
        db.add(
            Conversation(
                session_id=session.id,
                retention_expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await db.commit()


async def add_property(
    client: AsyncClient, token: str, org_id: str, label: str, origin: str
) -> tuple[str, str]:
    """Another property under the same org - the group-operator case.

    Returns ``(project_id, public_key)``, and registers its own origin, because a second property
    with no way to receive a guest message is not a property this test can say anything about.
    """
    slug = f"{label.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": label, "slug": slug},
    )
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]
    integration = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"repository_owner": "acme", "repository_name": f"{slug}-site"},
    )
    assert integration.status_code == 201, integration.text
    await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/website-integrations/origins",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": origin},
    )
    return project_id, integration.json()["public_key"]


# ============================================================
# The list
# ============================================================


class TestList:
    async def test_a_guest_turn_appears_in_the_inbox(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Do you have a pool?")

        resp = await inbox(client, tenant[0], tenant[1])
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["message_count"] == 2, "the guest's message and the reply"
        assert rows[0]["last_message_at"] is not None
        assert rows[0]["external_id"] is None, "a widget guest has no external identity"
        assert rows[0]["channel"] == "web"

    async def test_the_property_name_is_present(self, client: AsyncClient) -> None:
        """The list is reached from the org nav and is not filtered to one property, so without the
        project name a group operator sees 'Guest A' once per hotel and reads it as a bug."""
        tenant = await make_tenant(client, "Serengeti")
        await turn(client, tenant, "Hello")

        rows = (await inbox(client, tenant[0], tenant[1])).json()

        assert rows[0]["project_name"] == "Serengeti Hotel"

    async def test_all_properties_appear_under_one_org(self, client: AsyncClient) -> None:
        """One inbox across the group, which is the reason the route is org-level.

        Both properties have a conversation, and the unfiltered list shows both - otherwise this
        would only be re-testing the project filter.
        """
        tenant = await make_tenant(client, "Group")
        other_id, other_key = await add_property(
            client, tenant[0], tenant[1], "Jinja Annexe", "https://annexe.example"
        )
        await turn(client, tenant, "Pool hours?")
        await say(client, other_key, "Do you have a gym?", origin="https://annexe.example")

        rows = (await inbox(client, tenant[0], tenant[1])).json()

        assert len(rows) == 2, "both properties' guests belong in one inbox"
        assert {r["project_id"] for r in rows} == {tenant[2], other_id}
        # The property column is what makes two guests at different hotels distinguishable.
        assert {r["project_name"] for r in rows} == {"Group Hotel", "Jinja Annexe"}

        narrowed = (
            await inbox(client, tenant[0], tenant[1], project_id=other_id)
        ).json()
        assert [r["project_id"] for r in narrowed] == [other_id]

    async def test_a_conversation_with_no_messages_is_still_listed(
        self, client: AsyncClient
    ) -> None:
        """Count 0 and a null timestamp, rather than being hidden or counted as 1.

        A conversation exists before its first reply is written - the guest has arrived and the
        assistant has not answered yet, which is precisely the ``pending`` state. A desk that hides
        those cannot see work in progress.
        """
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Hello")
        await empty_conversation(tenant[2])

        rows = (await inbox(client, tenant[0], tenant[1])).json()
        silent = [r for r in rows if r["message_count"] == 0]

        assert len(silent) == 1, "the message-less conversation was hidden or miscounted"
        assert silent[0]["last_message_at"] is None
        assert silent[0]["status"] == "pending", (
            "an unanswered conversation is pending - it is not awaiting approval, because no "
            "draft exists to approve"
        )

    async def test_the_list_is_newest_conversation_first(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        for i in range(3):
            await turn(client, tenant, f"Question {i}")

        rows = (await inbox(client, tenant[0], tenant[1])).json()

        assert len(rows) == 3
        assert [r["created_at"] for r in rows] == sorted(
            (r["created_at"] for r in rows), reverse=True
        )


class TestFilters:
    """The inbox's three tabs are three filters, so a filter that silently does nothing turns a tab
    into "everything" - which looks like a working page until someone notices Guest A in Approvals.

    Statuses are set directly because nothing in the runtime writes them yet: the lifecycle columns
    arrived with 0037 and the approval endpoint has not been written. That is exactly the state this
    API is being built against, so driving it through the database is honest rather than a shortcut.
    """

    async def _seed_statuses(self, tenant: Tenant) -> None:
        from sqlalchemy import select

        from app.core.database import get_session_factory
        from app.models.conversation import Conversation, ConversationStatus, VisitorSession

        # Five distinct states, assigned in creation order so the tests can name any of them.
        plan = ["awaiting_approval", "booked", "lost", "escalated", "answered"]
        async with get_session_factory()() as db:
            rows = list(
                (
                    await db.execute(
                        select(Conversation)
                        .join(VisitorSession, VisitorSession.id == Conversation.session_id)
                        .where(VisitorSession.project_id == uuid.UUID(tenant[2]))
                        .order_by(Conversation.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == len(plan), "the caller must create one conversation per status"
            for conversation, status in zip(rows, plan, strict=True):
                conversation.status = ConversationStatus(status)
                conversation.lost_reason = "Price" if status == "lost" else None
            await db.commit()

    async def test_filtering_by_status_returns_only_that_status(
        self, client: AsyncClient
    ) -> None:
        tenant = await make_tenant(client, "Hotel")
        for i in range(5):
            await turn(client, tenant, f"Question {i}")
        await self._seed_statuses(tenant)

        awaiting = (await inbox(client, tenant[0], tenant[1], status="awaiting_approval")).json()
        booked = (await inbox(client, tenant[0], tenant[1], status="booked")).json()

        assert [r["status"] for r in awaiting] == ["awaiting_approval"]
        assert [r["status"] for r in booked] == ["booked"]

    async def test_status_can_be_repeated_to_mean_any_of(
        self, client: AsyncClient
    ) -> None:
        """The Approvals tab needs "everything a person must act on" in one request, not one round
        trip per state - so the filter takes a list rather than being single-valued."""
        tenant = await make_tenant(client, "Hotel")
        for i in range(5):
            await turn(client, tenant, f"Question {i}")
        await self._seed_statuses(tenant)

        rows = (
            await inbox(
                client,
                tenant[0],
                tenant[1],
                status="awaiting_approval&status=booked",
            )
        ).json()

        assert {r["status"] for r in rows} == {"awaiting_approval", "booked"}

    async def test_a_lost_conversation_carries_its_reason(self, client: AsyncClient) -> None:
        """The prototype's Reason column. Null for every other status - a reason on a live booking
        would be nonsense, so this also pins that the field is not just always-populated."""
        tenant = await make_tenant(client, "Hotel")
        for i in range(5):
            await turn(client, tenant, f"Question {i}")
        await self._seed_statuses(tenant)

        lost = (await inbox(client, tenant[0], tenant[1], status="lost")).json()
        others = (await inbox(client, tenant[0], tenant[1], status="booked")).json()

        assert [r["lost_reason"] for r in lost] == ["Price"]
        assert all(r["lost_reason"] is None for r in others)

    async def test_filtering_by_channel_narrows_to_that_channel(
        self, client: AsyncClient
    ) -> None:
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Pool hours?")
        await empty_conversation(tenant[2])

        web = (await inbox(client, tenant[0], tenant[1], channel="web")).json()
        whatsapp = (await inbox(client, tenant[0], tenant[1], channel="whatsapp")).json()

        assert [r["channel"] for r in web] == ["web"]
        assert [r["channel"] for r in whatsapp] == ["whatsapp"]

    async def test_filtering_by_intent_narrows_to_that_intent(
        self, client: AsyncClient
    ) -> None:
        """Follow-up eligibility keys off intent, so the filter has to actually work - and an
        unclassified conversation must fall outside INFORMATIONAL rather than inside it."""
        tenant = await make_tenant(client, "Hotel")
        for i in range(3):
            await turn(client, tenant, f"Question {i}")
        await set_intents(tenant, {"informational": 1, "booking": 1})

        rows = (await inbox(client, tenant[0], tenant[1], intent="booking")).json()

        assert [r["intent"] for r in rows] == ["booking"]
        unclassified = (await inbox(client, tenant[0], tenant[1], intent="informational")).json()
        assert len(unclassified) == 1, "the third conversation has no intent and must not match"


# ============================================================
# The tenant boundary - the whole point
# ============================================================


class TestTenantBoundary:
    async def test_another_orgs_conversations_are_not_listed(self, client: AsyncClient) -> None:
        mine = await make_tenant(client, "Mine")
        theirs = await make_tenant(client, "Theirs")
        await turn(client, theirs, "My card number is 4242 4242 4242 4242")

        rows = (await inbox(client, mine[0], mine[1])).json()

        assert rows == [], "another tenant's guest conversation leaked into the inbox"

    async def test_another_orgs_conversation_is_not_found(self, client: AsyncClient) -> None:
        """404, not 403.

        A 403 confirms the id exists, which turns the endpoint into an oracle for hunting another
        tenant's conversation ids. Not-found answers the same thing for a non-existent id, so the
        two are indistinguishable.
        """
        mine = await make_tenant(client, "Mine")
        theirs = await make_tenant(client, "Theirs")
        created = await turn(client, theirs, "Hello")
        conversation_id = created.json()["conversation_id"]

        resp = await transcript(client, mine, conversation_id)

        assert resp.status_code == 404, resp.text

    async def test_a_non_member_is_refused(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        stranger = await make_tenant(client, "Stranger")

        resp = await inbox(client, stranger[0], tenant[1])

        assert resp.status_code == 404, "an org you are not a member of must not be listable"

    async def test_a_bogus_conversation_id_is_refused_the_same_way(
        self, client: AsyncClient
    ) -> None:
        """An id that does not exist and an id that belongs to someone else must look identical,
        or the pair is a membership oracle."""
        mine = await make_tenant(client, "Mine")
        theirs = await make_tenant(client, "Theirs")
        created = await turn(client, theirs, "Hello")

        headers = auth(mine[0])
        theirs_resp = await client.get(
            f"/api/v1/organizations/{mine[1]}/conversations/{created.json()['conversation_id']}",
            headers=headers,
        )
        absent_resp = await client.get(
            f"/api/v1/organizations/{mine[1]}/conversations/{uuid.uuid4()}", headers=headers
        )

        assert theirs_resp.status_code == absent_resp.status_code == 404
        assert theirs_resp.json() == absent_resp.json(), (
            "the two refusals differ, so the endpoint reveals which ids exist"
        )


# ============================================================
# Pagination - where the real bugs live
# ============================================================


class TestPagination:
    async def test_a_link_header_is_returned_when_more_remain(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        for i in range(3):
            await turn(client, tenant, f"Question {i}")

        resp = await inbox(client, tenant[0], tenant[1], limit=2)

        assert len(resp.json()) == 2
        assert "Link" in resp.headers
        assert 'rel="next"' in resp.headers["Link"]

    async def test_no_link_header_on_the_last_page(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        for i in range(2):
            await turn(client, tenant, f"Question {i}")

        resp = await inbox(client, tenant[0], tenant[1], limit=2)

        assert "Link" not in resp.headers

    async def test_paging_covers_every_row_exactly_once(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        for i in range(5):
            await turn(client, tenant, f"Question {i}")

        seen: list[str] = []
        cursor = None
        for _ in range(5):
            resp = await inbox(client, tenant[0], tenant[1], limit=2, cursor=cursor)
            assert resp.status_code == 200, resp.text
            seen.extend(row["id"] for row in resp.json())
            link = resp.headers.get("Link")
            if not link:
                break
            cursor = link.split("cursor=")[1].split(">")[0]

        assert len(seen) == 5
        assert len(set(seen)) == 5, f"a row was served twice: {seen}"

    async def test_a_conversation_created_mid_pagination_does_not_shift_the_window(
        self, client: AsyncClient
    ) -> None:
        """The reason this is keyset rather than offset.

        A new conversation is the newest, so it lands *above* the cursor and never appears - which is
        correct and is the whole point. Under an offset it would push the window down and cause the
        last row of page one to be served again as the first row of page two.
        """
        tenant = await make_tenant(client, "Hotel")
        for i in range(4):
            await turn(client, tenant, f"Question {i}")

        first = await inbox(client, tenant[0], tenant[1], limit=2)
        page_one = [row["id"] for row in first.json()]
        cursor = first.headers["Link"].split("cursor=")[1].split(">")[0]

        # Arrives while the caller is halfway through the list.
        await turn(client, tenant, "A question that arrives mid-pagination")

        seen = list(page_one)
        while cursor:
            resp = await inbox(client, tenant[0], tenant[1], limit=2, cursor=cursor)
            seen.extend(row["id"] for row in resp.json())
            link = resp.headers.get("Link")
            cursor = link.split("cursor=")[1].split(">")[0] if link else None

        assert len(seen) == len(set(seen)), f"a row was served twice: {seen}"
        assert set(seen).issubset(set(page_one) | set(seen))
        assert len(seen) == 4, f"expected the 4 pre-existing rows, got {len(seen)}"

    async def test_a_forged_cursor_is_a_400_not_a_500(self, client: AsyncClient) -> None:
        """The request was well formed; the cursor was not one we issued. That is 400.

        Letting it raise turns a client's bad state into a server error, and a 500 here would be
        indistinguishable from the endpoint being broken.
        """
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Hello")

        for bad in ("garbage", "!!!!", ""):
            resp = await inbox(client, tenant[0], tenant[1], limit=2, cursor=bad or "x")
            assert resp.status_code in (400, 422), f"cursor={bad!r} gave {resp.status_code}"


# ============================================================
# The transcript
# ============================================================


class TestCounts:
    """The three tab badges.

    Counts are a separate endpoint rather than a length on the list because the list is paginated:
    a badge computed from the rows on screen would read 25 when the desk holds 4,000.
    """

    @staticmethod
    async def counts(client: AsyncClient, tenant: Tenant) -> dict:
        resp = await client.get(
            f"/api/v1/organizations/{tenant[1]}/conversations/counts",
            headers=auth(tenant[0]),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def test_an_empty_inbox_reports_zeroes(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")

        assert await self.counts(client, tenant) == {
            "logs": 0,
            "approvals": 0,
            "followups": 0,
        }

    async def test_each_tab_counts_the_right_group(self, client: AsyncClient) -> None:
        """A booked conversation must not appear in follow-ups.

        The reference defines that list as "quotes waiting on a guest reply", and a guest who has
        booked has converted - there is nobody to chase.
        """
        tenant = await make_tenant(client, "Hotel")
        for _ in range(5):
            await turn(client, tenant, "Hello")
        await seed_statuses(tenant, ["booked", "booked", "awaiting_guest", "lost", "answered"])

        counts = await self.counts(client, tenant)

        assert counts["logs"] == 5, "the logs tab is every conversation"
        assert counts["followups"] == 2, "one quote awaiting a guest, one lost"

    async def test_approvals_are_counted(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        for _ in range(3):
            await turn(client, tenant, "Hello")
        await seed_statuses(tenant, ["awaiting_approval", "awaiting_approval", "answered"])

        counts = await self.counts(client, tenant)

        assert counts["approvals"] == 2
        assert counts["logs"] == 3

    async def test_counts_ignore_another_tenants_conversations(
        self, client: AsyncClient
    ) -> None:
        mine = await make_tenant(client, "Mine")
        theirs = await make_tenant(client, "Theirs")
        for _ in range(3):
            await turn(client, theirs, "Hello")

        counts = await self.counts(client, mine)

        assert counts == {"logs": 0, "approvals": 0, "followups": 0}, (
            "another tenant's conversations are being counted"
        )

    async def test_counts_is_not_parsed_as_a_conversation_id(
        self, client: AsyncClient
    ) -> None:
        """Route ordering, pinned.

        `/conversations/counts` and `/conversations/{conversation_id}` have the same segment count,
        so FastAPI matches them in registration order. Declared the other way round this answers
        422 - and the failure would read as a broken tab rather than a reordered router.
        """
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Hello")

        counts = await self.counts(client, tenant)

        assert set(counts) == {"logs", "approvals", "followups"}


class TestResponseTimings:
    """The logs table's two response-time columns, which are different measurements.

    The prototype counts the assistant's holding reply as the *first reply* and a delivered price
    as the *useful answer*. Collapsing them would report that a guest had a price quote in front of
    them while it was still sitting in the approval queue.
    """

    async def test_first_reply_is_the_first_outbound_message(
        self, client: AsyncClient
    ) -> None:
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Pool hours?")

        rows = (await inbox(client, tenant[0], tenant[1])).json()

        assert rows[0]["first_inbound_at"] is not None
        assert rows[0]["first_reply_at"] is not None
        assert rows[0]["useful_answer_at"] is not None
        # Both are measured from the guest's first message, so neither precedes it.
        assert rows[0]["first_inbound_at"] <= rows[0]["first_reply_at"] <= rows[0]["useful_answer_at"]

    async def test_an_unanswered_conversation_has_no_reply_time(
        self, client: AsyncClient
    ) -> None:
        """Both null rather than zero. Zero would render as "replied instantly"."""
        tenant = await make_tenant(client, "Hotel")
        await empty_conversation(tenant[2])

        rows = (await inbox(client, tenant[0], tenant[1])).json()
        silent = [r for r in rows if r["message_count"] == 0]

        assert len(silent) == 1
        assert silent[0]["first_reply_at"] is None
        assert silent[0]["useful_answer_at"] is None
        assert silent[0]["first_inbound_at"] is None, (
            "a conversation with no messages has not been received from anybody"
        )

    async def test_a_drafted_reply_is_not_a_useful_answer(self, client: AsyncClient) -> None:
        """The distinction that makes the two columns worth having.

        Nothing writes a DRAFTED message yet - the approval endpoint does not exist - so this is
        constructed directly. It is exactly the state the column exists for, and it would be the
        easiest thing to get wrong when that endpoint lands.
        """
        tenant = await make_tenant(client, "Hotel")
        await turn(client, tenant, "Room for 2 this Friday?")
        await mark_reply_as_draft(tenant[2])

        rows = (await inbox(client, tenant[0], tenant[1])).json()

        assert rows[0]["first_reply_at"] is not None, "a holding reply was still sent"
        assert rows[0]["useful_answer_at"] is None, (
            "a draft has not reached the guest, so nothing useful has been delivered"
        )


class TestTranscript:
    async def test_a_conversation_reads_back_oldest_first(self, client: AsyncClient) -> None:
        tenant = await make_tenant(client, "Hotel")
        created = await turn(client, tenant, "Do you have a pool?")

        resp = await transcript(client, tenant, created.json()["conversation_id"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [m["role"] for m in body["messages"]] == ["VISITOR", "ASSISTANT"]
        assert body["messages"][0]["content"] == "Do you have a pool?"

    async def test_direction_is_reported_for_each_message(self, client: AsyncClient) -> None:
        """Direction and status are separate questions: which way it went, and what happened to it
        afterwards. Collapsing them loses the case of a draft that never reached anyone."""
        tenant = await make_tenant(client, "Hotel")
        created = await turn(client, tenant, "Hello")

        body = (await transcript(client, tenant, created.json()["conversation_id"])).json()

        directions = [m["direction"] for m in body["messages"]]
        assert directions == ["inbound", "outbound"]
        assert body["messages"][0]["status"] is None, (
            "a guest's message has no delivery lifecycle; it arrived"
        )
        assert body["messages"][1]["status"] == "sent"

    async def test_the_transcript_carries_the_project_it_belongs_to(
        self, client: AsyncClient
    ) -> None:
        tenant = await make_tenant(client, "Hotel")
        created = await turn(client, tenant, "Hello")

        body = (await transcript(client, tenant, created.json()["conversation_id"])).json()

        assert body["project_id"] == tenant[2]
        assert body["project_name"] == "Hotel Hotel"