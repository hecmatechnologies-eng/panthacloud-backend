"""The channel entry to the runtime (ADR-004).

The claim this file exists to check is that a channel turn is *not* a second pipeline. It resolves
to a session by identity rather than by a client-supplied id, but from there it runs the same code
the widget runs: same bounds, same persistence, same outbound PII guard. If ``handle_channel_message``
ever grew its own shortcut around ``complete_turn``, the tests below fail - which is the point of
putting the entry in ``app/runtime/chat.py`` instead of in an adapter.

Three of these are specifically about ways the channel path could quietly get less safe than the
widget: skipping the outbound guard, sharing a rate-limit bucket with every other channel tenant, and
leaking one tenant's conversation to another.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel, ChannelIdentity
from app.core.database import get_session_factory
from app.llm.gateway import ModelGateway, set_model_gateway
from app.llm.providers.fake import FakeModelProvider
from app.models.conversation import (
    Conversation,
    Message,
    MessageDirection,
    MessageRole,
    MessageStatus,
    VisitorSession,
)
from app.models.model_usage import ModelUsage
from app.runtime.chat import handle_channel_message
from app.runtime.rate_limit import rate_limiter
from app.runtime.resolver import channel_context

_FAKE: dict = {}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(autouse=True)
def _model_gateway():
    provider = FakeModelProvider(reply="Your booking is confirmed.")
    set_model_gateway(ModelGateway(provider))
    _FAKE["provider"] = provider
    yield
    set_model_gateway(None)
    _FAKE.clear()


# ============================================================
# Fixtures / helpers
# ============================================================


async def make_project(client: AsyncClient, label: str) -> tuple[str, str]:
    """A registered user, org and project. Returns ``(organization_id, project_id)``."""
    suffix = uuid.uuid4().hex[:8]
    # Labels are read nicely in failures ("Hotel A") but an address cannot carry their spaces.
    handle = label.lower().replace(" ", "")
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{handle}-{suffix}@example.com",
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
        json={"name": label, "slug": f"{handle}-{suffix}"},
    )
    assert proj.status_code == 201, proj.text
    return org_id, proj.json()["id"]


def wa(number: str = "256772123456", thread: str | None = None) -> ChannelIdentity:
    return ChannelIdentity(channel=Channel.WHATSAPP, external_id=number, thread_id=thread)


async def say(
    db: AsyncSession,
    org_id: str,
    project_id: str,
    text: str,
    identity: ChannelIdentity | None = None,
    client_ip: str | None = None,
):
    """One channel turn, committed - the same shape as the widget's per-request commit."""
    reply = await handle_channel_message(
        db,
        ctx=channel_context(
            organization_id=uuid.UUID(org_id), project_id=uuid.UUID(project_id)
        ),
        identity=identity or wa(),
        message=text,
        client_ip=client_ip,
    )
    await db.commit()
    return reply


async def session_for(project_id: str, external_id: str) -> VisitorSession | None:
    async with get_session_factory()() as db:
        return (
            await db.execute(
                select(VisitorSession).where(
                    VisitorSession.project_id == uuid.UUID(project_id),
                    VisitorSession.external_id == external_id,
                )
            )
        ).scalar_one_or_none()


async def messages_of(conversation_id: uuid.UUID) -> list[Message]:
    async with get_session_factory()() as db:
        return list(
            (
                await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at, Message.role)
                )
            ).scalars().all()
        )


# ============================================================
# The session a channel turn lands in
# ============================================================


class TestChannelSession:
    async def test_a_first_message_opens_a_session_with_no_widget_behind_it(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        org_id, project_id = await make_project(client, "Hotel")

        reply = await say(db_session, org_id, project_id, "Do you have a pool?")

        session = await session_for(project_id, "256772123456")
        assert session is not None
        assert session.channel is Channel.WHATSAPP
        assert session.integration_id is None, "a phone number has no widget behind it"
        assert session.origin is None, "and no browser origin"
        assert reply.session_id == session.id

    async def test_the_same_guest_keeps_one_session_and_one_conversation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        org_id, project_id = await make_project(client, "Hotel")

        first = await say(db_session, org_id, project_id, "Do you have a pool?")
        second = await say(db_session, org_id, project_id, "And a gym?")

        assert second.session_id == first.session_id
        assert second.conversation_id == first.conversation_id
        assert len(await messages_of(first.conversation_id)) == 4

    async def test_a_leading_plus_is_the_same_guest(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The provider and the guest's own signature disagree about the '+'; they are one person."""
        org_id, project_id = await make_project(client, "Hotel")

        first = await say(db_session, org_id, project_id, "Hello", identity=wa("+256772123456"))
        second = await say(db_session, org_id, project_id, "Hello again", identity=wa("256772123456"))

        assert second.session_id == first.session_id

    async def test_one_number_under_two_projects_is_two_conversations(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A guest may talk to two hotels. They are two conversations, and neither can see the other.

        This is the tenancy boundary the channel path is most likely to get wrong, because the
        speaker's identity is the same on both sides - only the resolved project differs.
        """
        org_a, project_a = await make_project(client, "Hotel A")
        org_b, project_b = await make_project(client, "Hotel B")

        a = await say(db_session, org_a, project_a, "What is the checkout time?")
        b = await say(db_session, org_b, project_b, "What is the checkin time?")

        assert a.session_id != b.session_id
        assert a.conversation_id != b.conversation_id

        # Hotel B's assistant has seen only Hotel B's question.
        seen_by_b = [m.content for m in await messages_of(b.conversation_id)]
        assert "What is the checkin time?" in seen_by_b
        assert not any("checkout" in c for c in seen_by_b)


# ============================================================
# The guards a channel turn must not get out of
# ============================================================


class TestTheSameGuardsApply:
    async def test_the_outbound_pii_guard_applies_to_a_channel_reply(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The reason this entry lives in the runtime rather than in an adapter.

        A model that invents a phone number in its reply gets it redacted on the channel path
        exactly as on the widget, and what is persisted is the redacted copy.
        """
        org_id, project_id = await make_project(client, "Hotel")
        _FAKE["provider"].reply = "Call us on +256 700 111 222 for the pool."

        reply = await say(db_session, org_id, project_id, "Do you have a pool?")

        assert "700 111 222" not in reply.reply
        stored = {m.content for m in await messages_of(reply.conversation_id)}
        assert reply.reply in stored, "the persisted copy is not the guarded copy that was returned"

    async def test_a_number_the_guest_supplied_survives_the_guard(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Redaction has to leave the guest's own data alone, or the reply is worse than useless."""
        org_id, project_id = await make_project(client, "Hotel")
        _FAKE["provider"].reply = "Noted, we have your number +256700555444 on file."

        reply = await say(
            db_session,
            org_id,
            project_id,
            "My number is +256700555444, please text me about the booking.",
        )

        assert "+256700555444" in reply.reply

    async def test_both_directions_are_recorded_as_such(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Same shape as a widget turn: the guest's message is inbound with no status - a guest's
        message was not 'sent', it arrived - and the reply is outbound and sent by definition.
        """
        org_id, project_id = await make_project(client, "Hotel")
        reply = await say(db_session, org_id, project_id, "Hello")

        rows = await messages_of(reply.conversation_id)
        inbound = [m for m in rows if m.role is MessageRole.VISITOR]
        outbound = [m for m in rows if m.role is MessageRole.ASSISTANT]

        assert [m.direction for m in inbound] == [MessageDirection.INBOUND]
        assert [m.direction for m in outbound] == [MessageDirection.OUTBOUND]
        assert inbound[0].status is None
        assert outbound[0].status is MessageStatus.SENT

    async def test_usage_is_recorded_without_an_integration(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The ledger's integration column is nullable with ON DELETE SET NULL, so a channel turn is
        accounted for against its project rather than dropped."""
        org_id, project_id = await make_project(client, "Hotel")

        await say(db_session, org_id, project_id, "Hello")

        async with get_session_factory()() as db:
            rows = (
                await db.execute(
                    select(ModelUsage).where(ModelUsage.project_id == uuid.UUID(project_id))
                )
            ).scalars().all()
        assert len(rows) == 1
        assert rows[0].integration_id is None
        assert rows[0].organization_id == uuid.UUID(org_id)

    async def test_a_channel_turn_is_bounded_by_its_project(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not by a bucket shared with every other channel tenant.

        ``integration_id`` is None here, and the obvious implementation stringifies it - which puts
        every channel conversation on the platform into one bucket that fills up on the busiest
        tenant's traffic and throttles everyone else. The bound has to be the tenancy anchor.
        """
        org_id, project_id = await make_project(client, "Hotel")
        seen: list[tuple[str, str]] = []
        real = rate_limiter.check

        async def spy(scope, key, limit, window):
            seen.append((scope, key))
            return await real(scope, key, limit, window)

        monkeypatch.setattr(rate_limiter, "check", spy)
        await say(db_session, org_id, project_id, "Hello")

        scopes = {scope for scope, _ in seen}
        assert "project" in scopes, f"a channel turn was not bounded by its project: {seen}"
        assert "integration" not in scopes, "a channel turn has no integration to be bounded by"
        assert not any(key == "None" for _, key in seen), f"a rate-limit key stringified None: {seen}"

    async def test_the_cheapest_bound_still_runs(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The IP shed moved out of ``_prepare_turn`` and into each entry point. Forgetting it on the
        channel entry would leave the one bound that costs a Redis round trip as the missing one."""
        org_id, project_id = await make_project(client, "Hotel")
        seen: list[tuple[str, str]] = []
        real = rate_limiter.check

        async def spy(scope, key, limit, window):
            seen.append((scope, key))
            return await real(scope, key, limit, window)

        monkeypatch.setattr(rate_limiter, "check", spy)
        await say(db_session, org_id, project_id, "Hello", client_ip="203.0.113.9")

        assert ("ip", "203.0.113.9") in seen


class TestConversationContinuity:
    async def test_a_second_turn_continues_the_same_conversation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """One conversation per session, and the second turn carries the first.

        What the assistant is shown is the whole point of a session existing, so a channel guest
        asking a follow-up must not be answered as a stranger.
        """
        org_id, project_id = await make_project(client, "Hotel")
        first = await say(db_session, org_id, project_id, "I have a booking under Adebayo.")
        second = await say(db_session, org_id, project_id, "What time is breakfast?")

        async with get_session_factory()() as db:
            conversation = (
                await db.execute(
                    select(Conversation).where(Conversation.id == second.conversation_id)
                )
            ).scalar_one()

        assert conversation.id == first.conversation_id

        rendered = "\n".join(m.content for m in _FAKE["provider"].calls[-1].messages)
        assert "Adebayo" in rendered, "the earlier turn was not in the context for the second turn"
        assert "What time is breakfast?" in rendered

    async def test_a_thread_is_its_own_conversation_with_the_same_person(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Support and bookings are one person's two conversations, not one muddled thread."""
        org_id, project_id = await make_project(client, "Hotel")
        support = await say(
            db_session, org_id, project_id, "The wifi is down", identity=wa(thread="support")
        )
        booking = await say(
            db_session, org_id, project_id, "Add a late checkout", identity=wa(thread="booking")
        )

        assert support.session_id != booking.session_id
        assert support.conversation_id != booking.conversation_id