"""The conversation lifecycle schema (migration 0037).

These are deliberately schema-level tests rather than behaviour tests. The two invariants that
matter most - that the assistant can never reach ``BOOKED``, and that a rejection returns to
``AWAITING_APPROVAL`` rather than to a state of its own - belong to the approval endpoint that does
not exist yet, and asserting them here would only be asserting that an enum exists.

What *can* be pinned now is the contract the inbox endpoint will be written against: that every
conversation is somewhere, that the starting state is the safe one, that ``intent`` is allowed to
say "not classified", and that the follow-up index is actually partial.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    Conversation,
    ConversationIntent,
    ConversationStatus,
    VisitorSession,
)


async def shape(db: AsyncSession) -> tuple[dict, list]:
    """The built table's columns and indexes, read through a sync connection.

    ``inspect`` refuses an AsyncEngine outright, so this goes via ``run_sync`` rather than reading
    the model - the point is to check the schema that was actually created, not the one the ORM
    believes it asked for.
    """

    def _read(conn):
        insp = inspect(conn)
        return (
            {c["name"]: c for c in insp.get_columns("conversations")},
            insp.get_indexes("conversations"),
        )

    async with db.bind.connect() as conn:
        return await conn.run_sync(_read)

# ============================================================
# The vocabulary
# ============================================================


class TestVocabulary:
    def test_every_status_is_the_shape_the_staff_ui_renders(self) -> None:
        """The prototype's states, corrected.

        `followup` is an activity that can overlap any status - chasing a guest is not a phase of
        the conversation - and `returned` is a rejected draft, which the draft message already
        records. Encoding either as a status would make a conversation claim to be two things.

        `pending` is the first entry because it is the state a conversation is born in: the guest
        has written and nobody has answered yet.
        """
        assert [s.value for s in ConversationStatus] == [
            "pending",
            "answered",
            "awaiting_approval",
            "escalated",
            "awaiting_guest",
            "booked",
            "lost",
        ]

    def test_no_status_claims_a_draft_exists_when_none_might(self) -> None:
        """`PENDING` and `AWAITING_APPROVAL` must stay distinct states, not be merged.

        An assistant that refuses to answer - which the runtime does, and correctly, per the eval
        corpus - produces no draft at all. If the initial state were AWAITING_APPROVAL, such a
        conversation would sit in the approval queue waiting for a person to approve nothing, and
        the inbox would render it as work that is not work.
        """
        assert ConversationStatus.PENDING.value == "pending"
        assert ConversationStatus.AWAITING_APPROVAL.value == "awaiting_approval"
        assert len({s.value for s in ConversationStatus}) == len(list(ConversationStatus))

    def test_every_value_is_lowercase_and_stable(self) -> None:
        """These strings are written to the database and read by the frontend, so they are a
        contract. A rename is a migration, which is why they are asserted rather than assumed."""
        for status in ConversationStatus:
            assert status.value == status.value.lower()
            assert " " not in status.value

    def test_intent_carries_the_rule_the_status_cannot(self) -> None:
        """*Info-only questions are not booking enquiries: no conversion, no follow-up.*

        That is a statement about what the guest wants, and follow-up eligibility keys off it. As a
        status it would be indistinguishable from an answered booking question.
        """
        assert {i.value for i in ConversationIntent} == {
            "informational",
            "booking",
            "event",
            "complaint",
            "other",
        }


class TestColumnShape:
    async def test_status_is_not_nullable(self, db_session: AsyncSession) -> None:
        """A conversation with no status is one the inbox cannot place, so the database refuses it
        rather than letting the write succeed and the read lie."""
        columns, _ = await shape(db_session)
        assert columns["status"]["nullable"] is False

    async def test_intent_is_nullable_on_purpose(self, db_session: AsyncSession) -> None:
        """Intent is an inference. An honest "not classified yet" is more useful than a default that
        silently becomes an eligibility decision about whether to chase this guest."""
        columns, _ = await shape(db_session)
        assert columns["intent"]["nullable"] is True

    async def test_the_follow_up_index_excludes_nulls(self, db_session: AsyncSession) -> None:
        """Almost every conversation has no follow-up scheduled, so an index over mostly-NULLs is an
        index over nothing. Verified against the built schema rather than assumed from the model,
        because a dropped ``sqlite_where``/``postgresql_where`` degrades quietly and invisibly."""
        _, indexes = await shape(db_session)
        follow_up = next(
            (ix for ix in indexes if ix["name"] == "ix_conversations_follow_up_due"), None
        )
        assert follow_up is not None, "the follow-up index is missing entirely"
        # `or` cannot be used here: a TextClause raises on __bool__, so the obvious
        # `a or b or c` raises instead of falling through. Compare against None explicitly.
        options = follow_up.get("dialect_options") or {}
        predicate = next(
            (
                str(candidate)
                for candidate in (
                    options.get("sqlite_where"),
                    options.get("postgresql_where"),
                    follow_up.get("where"),
                )
                if candidate is not None
            ),
            "",
        )
        assert "next_follow_up_at IS NOT NULL" in predicate, (
            f"the follow-up index is not partial, so it indexes every NULL: {follow_up}"
        )

    async def test_this_table_does_not_claim_to_know_its_project(
        self, db_session: AsyncSession
    ) -> None:
        """This table has no ``project_id``, and must not grow one.

        The anchor lives on ``VisitorSession``, one row per session, so the inbox filters by joining.
        Copying it down would be denormalisation for the sake of an index, and would create two
        columns that can disagree about which project owns a conversation.
        """
        columns, _ = await shape(db_session)
        assert "project_id" not in columns


# ============================================================
# Defaults, which are a policy decision
# ============================================================


async def _conversation(db: AsyncSession, **kwargs) -> Conversation:
    session = VisitorSession(
        project_id=kwargs.pop("project_id", uuid.uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(session)
    await db.flush()
    conversation = Conversation(
        session_id=session.id,
        retention_expires_at=datetime.now(UTC) + timedelta(days=7),
        **kwargs,
    )
    db.add(conversation)
    await db.flush()
    return conversation


class TestDefaults:
    async def test_a_new_conversation_is_pending(self, db_session: AsyncSession) -> None:
        """The default is `PENDING`: the latest guest message has not been answered.

        Not `ANSWERED`, because that asserts the assistant handled a message it has not seen. And
        deliberately not `AWAITING_APPROVAL`, which would assert a *draft exists and a person is
        blocked on it* - false for any conversation the assistant declines to answer, and the
        runtime declines regularly and correctly.
        """
        conversation = await _conversation(db_session)

        assert conversation.status is ConversationStatus.PENDING

    async def test_a_conversation_with_no_draft_is_not_in_the_approval_queue(
        self, db_session: AsyncSession
    ) -> None:
        """The concrete consequence, asserted rather than left as a comment.

        A brand-new conversation has no message at all, let alone a drafted reply. If it landed in
        AWAITING_APPROVAL, the Approvals tab - whose entire job is showing drafts a person can send -
        would list something with nothing to send.
        """
        conversation = await _conversation(db_session)

        assert conversation.status is not ConversationStatus.AWAITING_APPROVAL
        assert conversation.status is not ConversationStatus.ANSWERED

    async def test_an_unclassified_conversation_has_no_intent(
        self, db_session: AsyncSession
    ) -> None:
        """Left NULL rather than defaulted to INFORMATIONAL.

        A default here would be an eligibility decision in disguise: INFORMATIONAL means "never
        follow up", so defaulting to it would silently switch off chasing every guest until
        something classified them.
        """
        conversation = await _conversation(db_session)

        assert conversation.intent is None

    async def test_the_status_survives_a_reload(self, db_session: AsyncSession) -> None:
        """The default is applied by the database, so it must read back as a real value rather than
        as a Python-side attribute that only exists in memory."""
        created = await _conversation(db_session)
        await db_session.commit()

        reloaded = (
            await db_session.execute(
                select(Conversation).where(Conversation.id == created.id)
            )
        ).scalar_one()

        assert reloaded.status is ConversationStatus.PENDING

    async def test_a_scheduled_follow_up_is_stored(self, db_session: AsyncSession) -> None:
        """A follow-up is a schedule, not a status - so it is a timestamp that can be cleared."""
        due = datetime.now(UTC) + timedelta(hours=24)
        conversation = await _conversation(
            db_session, status=ConversationStatus.AWAITING_GUEST, next_follow_up_at=due
        )

        assert conversation.next_follow_up_at is not None
        assert conversation.status is ConversationStatus.AWAITING_GUEST


class TestLostReason:
    async def test_a_lost_reason_is_kept_separately_from_the_status(
        self, db_session: AsyncSession
    ) -> None:
        """Why they did not book is a different fact from the fact that they did not.

        Keeping them in one column would lose the distinction between "closed, no reason recorded"
        and "closed because of price" - and the first is a conversation still needing an answer.
        """
        conversation = await _conversation(
            db_session, status=ConversationStatus.LOST, lost_reason="Price"
        )

        assert conversation.status is ConversationStatus.LOST
        assert conversation.lost_reason == "Price"

    async def test_a_lost_conversation_can_have_no_reason_yet(
        self, db_session: AsyncSession
    ) -> None:
        """Legal, and deliberately so: the status closes the conversation, the reason is captured
        when the guest or the desk supplies one.

        Deriving a reason from silence - the thing K3's idle analyser would have produced - would
        make this field a guess presented as a fact.
        """
        conversation = await _conversation(db_session, status=ConversationStatus.LOST)

        assert conversation.lost_reason is None


class TestRetentionStillIndependent:
    async def test_lifecycle_did_not_absorb_the_retention_timestamp(
        self, db_session: AsyncSession
    ) -> None:
        """`retention_expires_at` is its own column and stays its own column.

        It is deliberately independent of the session TTL (FR-056): a session can lapse while the
        conversation's content is still inside its retention window. Adding lifecycle state is
        exactly the kind of change that quietly collapses those two into one.
        """
        created = await _conversation(db_session)
        await db_session.commit()

        reloaded = (
            await db_session.execute(
                select(Conversation).where(Conversation.id == created.id)
            )
        ).scalar_one()

        assert reloaded.retention_expires_at is not None