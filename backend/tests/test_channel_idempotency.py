"""A retried webhook delivery must not duplicate the guest's turn.

Every provider retries: a slow answer is ambiguous from Meta's side, so the same ``wamid`` arrives
twice. Without handling, the guest's transcript gains a second copy of the same sentence and the
guest is visibly answered twice.

The uniqueness is enforced by ``uq_message_external_id`` and the duplicate is absorbed in
``_persist_inbound``, not pre-checked in the adapter - a pre-check races a concurrent retry and
both would write. These tests cover both halves: that the id is recorded, and that a repeat does not
add a row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.channels.base import Channel, ChannelIdentity
from app.models.conversation import Conversation, Message, MessageDirection, VisitorSession

WA_ID = "256700111222"
WAMID = "wamid.ABC123"


@pytest.fixture
async def conversation(db_session):
    """A session and conversation in the shape a channel turn creates."""
    session = VisitorSession(
        project_id=uuid.uuid4(),
        integration_id=None,
        channel=Channel.WHATSAPP,
        external_id=WA_ID,
        thread_id="",
        origin=None,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db_session.add(session)
    await db_session.flush()

    conversation = Conversation(
        session_id=session.id,
        retention_expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    db_session.add(conversation)
    await db_session.commit()
    return conversation


async def _count(db, conversation_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
    ).scalar_one()


class TestProviderRetries:
    async def test_the_provider_message_id_is_recorded(self, db_session, conversation) -> None:
        from app.runtime.chat import _persist_inbound

        await _persist_inbound(
            db_session, conversation_id=conversation.id, content="Do you have a room?",
            message_id=WAMID,
        )
        await db_session.commit()

        row = (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        ).scalars().one()

        assert row.external_message_id == WAMID
        assert row.direction is MessageDirection.INBOUND

    async def test_a_retry_does_not_add_a_second_row(self, db_session, conversation) -> None:
        from app.runtime.chat import _persist_inbound

        for _ in range(3):  # the same delivery, three times
            await _persist_inbound(
                db_session, conversation_id=conversation.id, content="Do you have a room?",
                message_id=WAMID,
            )
        await db_session.commit()

        assert await _count(db_session, conversation.id) == 1

    async def test_distinct_messages_are_all_kept(self, db_session, conversation) -> None:
        """The guard must be on the id, not on the content.

        A guest asking the same thing twice is two real messages and both belong in the transcript.
        """
        from app.runtime.chat import _persist_inbound

        for mid in ("wamid.1", "wamid.2"):
            await _persist_inbound(
                db_session, conversation_id=conversation.id, content="Do you have a room?",
                message_id=mid,
            )
        await db_session.commit()

        assert await _count(db_session, conversation.id) == 2

    async def test_a_channel_without_a_provider_id_still_writes(self, db_session, conversation) -> None:
        """The widget has no provider message id, and NULLs must not collide.

        The unique index is partial on `IS NOT NULL` precisely so every widget turn can leave it
        unset; without that predicate the second widget turn in a conversation would be an
        IntegrityError.
        """
        from app.runtime.chat import _persist_inbound

        for _ in range(2):
            await _persist_inbound(
                db_session, conversation_id=conversation.id, content="hello", message_id=None
            )
        await db_session.commit()

        assert await _count(db_session, conversation.id) == 2


class TestIdentity:
    def test_a_channel_turn_carries_the_provider_id(self) -> None:
        from app.runtime.chat import ChannelTurn

        turn = ChannelTurn(
            ctx=None,  # type: ignore[arg-type]  # not used by this assertion
            identity=ChannelIdentity(channel=Channel.WHATSAPP, external_id=WA_ID),
            message_id=WAMID,
        )

        assert turn.message_id == WAMID

    def test_it_defaults_to_absent_for_a_channel_that_has_none(self) -> None:
        from app.runtime.chat import ChannelTurn

        turn = ChannelTurn(
            ctx=None,  # type: ignore[arg-type]
            identity=ChannelIdentity(channel=Channel.SMS, external_id="+256700000000"),
        )

        assert turn.message_id is None