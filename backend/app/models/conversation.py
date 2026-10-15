"""Visitor conversation memory (FR-056, FR-119–121).

The runtime plane's store: one ``VisitorSession`` per visitor browser session, its
``Conversation`` threads, and their ``Message`` turns. A separate tier from engineering
conversations by construction — nothing here is reachable from the control plane's
``IntegrationRun`` records.

Tenancy is carried by the path ``WebsiteIntegration → Project → Organization``; there is no
organization column to keep in sync. Deleting the integration, project or organization cascades
all the way to messages, which is the deletion path FR-119/FR-120 require.

The cascade that actually deletes is the **ORM relationship cascade**, not the migration's
``ondelete="CASCADE"``: SQLite runs with the ``foreign_keys`` pragma off, so the FK clause is
inert there and the ORM is what removes children. The ``ondelete`` clause is a Postgres backstop.
A future retention sweep that deletes in bulk must therefore go through the ORM (or enable the
pragma), or it will orphan conversations and messages on SQLite.

Nothing writes to these tables yet — B4 is the first endpoint that does.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID

from app.channels.base import Channel
from app.core.origins import MAX_ORIGIN_LENGTH
from app.models.base import BaseModel
from app.models.knowledge import JSONType

if TYPE_CHECKING:
    from app.models.website_integration import WebsiteIntegration


class MessageRole(str, enum.Enum):
    VISITOR = "VISITOR"
    ASSISTANT = "ASSISTANT"
    #: A staff member replying, rather than the assistant. Distinct from ``ASSISTANT`` because the
    #: two have different accountability: an assistant answer is model output, a staff reply is a
    #: person speaking for the business. K5's approval gate is what makes this reachable.
    HUMAN_OPERATOR = "HUMAN_OPERATOR"


class MessageDirection(str, enum.Enum):
    #: Toward the guest. Providers retry webhooks, so an inbound turn can arrive twice and the
    #: duplicate must be refused rather than written.
    INBOUND = "inbound"
    #: Away from the guest, over whatever channel the session came in on.
    OUTBOUND = "outbound"


class MessageStatus(str, enum.Enum):
    """Delivery lifecycle for an outbound turn.

    Null on inbound rows: a guest's message has no delivery state, and making it say
    ``SENT`` would be a fiction that any query filtering on status has to special-case.
    """

    #: Composed but not yet sent - the K5 approval state.
    DRAFTED = "drafted"
    AWAITING_APPROVAL = "awaiting_approval"
    SENT = "sent"
    FAILED = "failed"


class VisitorSession(BaseModel):
    """One visitor's conversation on one channel (FR-108, FR-113).

    Scoped by ``project_id``, not by ``integration_id``. That inverts the original design on
    purpose: a session used to require a website integration because the widget was the only
    channel, and ``integration_id`` doubled as the tenancy anchor. It is now provenance only - "this
    conversation started on that widget" - and nullable, because a WhatsApp or email conversation
    has no widget behind it and the alternative is a column that forbids every channel we are
    building.

    ``project_id`` is the anchor because every turn needs one: ``KnowledgeBase`` and ``Assistant``
    are project-scoped, and ``Project.organization_id`` already carries the organisation, so adding
    an ``organization_id`` here would only denormalise it.

    ``channel``/``external_id``/``thread_id`` are the normalised conversation key for non-widget
    channels (ADR-004). ``external_id`` is opaque and never parsed - a Telegram chat id is not a
    phone number. It is NULL on widget rows, which is what keeps them out of the channel index.
    """

    __tablename__ = "visitor_sessions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_integrations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Which channel this conversation arrived on. The enum values are stored, so renaming one is
    # a migration; the set is expected to grow with channels.
    channel: Mapped[Channel] = mapped_column(
        SQLEnum(Channel, name="session_channel", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=Channel.WEB,
    )
    # The provider's own identifier for the person or conversation. Opaque: never parsed, never
    # normalised beyond whitespace, because a provider's format is theirs to change.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Separates distinct conversations with the same person. Some providers supply it, some must
    # derive it.
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The canonical origin the session was created from, as returned by the resolver. Stored so a
    # later turn can be bound to the origin it began under. Widget-only: a phone number has no
    # origin header.
    origin: Mapped[str | None] = mapped_column(
        String(MAX_ORIGIN_LENGTH),
        nullable=True,
    )
    # Session validity TTL. A retention field: enforced by the runtime, not the database.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    integration: Mapped["WebsiteIntegration | None"] = relationship(
        "WebsiteIntegration",
        back_populates="visitor_sessions",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Conversation.created_at",
    )

    __table_args__ = (
        # One live conversation per person per channel per project.
        #
        # Partial on `external_id IS NOT NULL`, which puts widget rows - every row with no external
        # id - outside the constraint's scope. Under the default in both engines NULLs are distinct,
        # so the predicate does not prevent a present collision; it stops the behaviour depending on
        # a default that Postgres 15+ can override per-type with NULLS NOT DISTINCT.
        #
        # `thread_id` is indexed as `coalesce(thread_id, '')`, and that is load-bearing rather than
        # defensive. A top-level conversation has no thread, so `thread_id` is NULL for the most
        # common rows there are - and NULLs are distinct *within the key*, so a plain column index
        # admits any number of them. Verified on both engines: three rows with thread_id of NULL,
        # '' and 'x' coexisted without complaint, which is the index not firing at all for exactly
        # the case the guarantee exists to cover. Two deliveries of one first message would then
        # each open a session and the guest would appear twice.
        #
        # Coalescing makes the key total, so no value can be written that escapes the constraint.
        # Canonical writes (see `app.channels.sessions`, which stores '') keep the column readable,
        # but the index does not depend on that: a writer that forgets still gets refused, rather
        # than silently losing uniqueness.
        #
        # The lookup coalesces identically, which keeps the query sargable against this exact
        # expression and matches rows written before the canonical form.
        #
        # Widget rows therefore keep no uniqueness guarantee of their own - deliberately the status
        # quo, where they are found by a client-supplied id rather than looked up by identity.
        # Enforcing it per origin would break a visitor who clears browser storage mid-visit.
        Index(
            "uq_visitor_session_channel_identity",
            "project_id",
            "channel",
            "external_id",
            func.coalesce(text("thread_id"), ""),
            unique=True,
            sqlite_where=text("external_id IS NOT NULL"),
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )


class ConversationStatus(str, enum.Enum):
    """Where a conversation is up to — one per conversation, and whose turn it is.

    Deliberately **not** ``MessageStatus``. A conversation can be ``AWAITING_GUEST`` while every
    one of its messages is ``SENT``, so folding the two together would lose a state that cannot be
    recovered from the messages.

    Only the question "whose turn is it?" belongs here. What the guest wants is ``intent``, how
    valuable they are is ``value``, and when to chase them is ``next_follow_up_at`` — all orthogonal,
    all columns on this table rather than members of this enum. The prototype this replaces listed
    ``followup`` and ``returned`` alongside the real states; the first is an activity inside
    "quote sent" and the second is a rejected draft, both of which are derivable from elsewhere.
    """

    #: The most recent guest message has not been answered yet - the reply is being produced, or the
    #: assistant decided there was nothing safe to send. This is the state a conversation is *born*
    #: in, and the one it returns to whenever a guest writes again.
    #:
    #: It is deliberately not "awaiting approval". That state claims a draft exists and a person is
    #: blocking on it, which is false for most conversations: an assistant that has refused to
    #: answer - which the runtime does, and correctly - produces no draft at all, so a conversation
    #: would sit in AWAITING_APPROVAL waiting for a human to approve nothing. A state that
    #: over-claims is worse than a missing one, because the inbox renders it as work.
    PENDING = "pending"
    #: The assistant answered from the knowledge base and nothing is owed. Terminal - but only
    #: when the intent is INFORMATIONAL; a booking enquiry answered and awaiting a reply is
    #: AWAITING_GUEST, not this.
    ANSWERED = "answered"
    #: A drafted reply exists and is waiting for a person. Rejection returns here rather than to a
    #: distinct state, so "the current draft was rejected" is read off the message.
    AWAITING_APPROVAL = "awaiting_approval"
    #: Handed to a human team; out of the assistant's hands.
    ESCALATED = "escalated"
    #: A reply has gone out and the guest owes the next move. This is where a quote lands, and the
    #: state from which a follow-up is due.
    AWAITING_GUEST = "awaiting_guest"
    #: The desk confirmed a booking. **Only a staff action can reach this** - see the invariant on
    #: :meth:`Message.can_be_confirmed_by_ai`.
    BOOKED = "booked"
    #: Closed without a booking, with the reason captured. Also staff- or guest-confirmed: in the
    #: prototype the guest replies "1" and the reason is recorded from that.
    LOST = "lost"


class ConversationIntent(str, enum.Enum):
    """What the guest wants, independent of where the conversation has got to.

    Separate from status because the two answer different questions and the rules key off both:
    *"info-only questions are not booking enquiries - no conversion, no follow-up"* is a statement
    about intent, and encoding it as a status would mean an answered booking question could not be
    told apart from an answered informational one.
    """

    #: A facilities, dining or policy question. Answered and done; never followed up.
    INFORMATIONAL = "informational"
    #: A room, a rate, a reservation.
    BOOKING = "booking"
    #: Conferences, weddings, group business. Usually escalated.
    EVENT = "event"
    #: A service failure. Never auto-answered.
    COMPLAINT = "complaint"
    #: Anything the classifier cannot place. Treated as INFORMATIONAL, because the safe default for
    #: an unrecognised request is to answer it and chase nobody.
    OTHER = "other"


class Conversation(BaseModel):
    """A visitor chat thread (FR-113, FR-119).

    Retention is deliberately its own timestamp, independent of the session TTL: a session can
    lapse while the conversation's content is still within its retention window (FR-056).
    """

    __tablename__ = "conversations"
    __table_args__ = (
        # Supports the follow-up sweep - "what is due, now" - without scanning. Partial, because
        # almost every conversation has a NULL here and an index over mostly-NULLs is an index over
        # nothing. Postgres and SQLite both honour the predicate.
        Index(
            "ix_conversations_follow_up_due",
            "next_follow_up_at",
            sqlite_where=text("next_follow_up_at IS NOT NULL"),
            postgresql_where=text("next_follow_up_at IS NOT NULL"),
        ),
        # Deliberately NOT indexed on (project_id, status): this table has no project_id. The anchor
        # lives on VisitorSession, one row per session, so the inbox filters by joining to it.
        # Copying the column down here would be denormalisation for the index's sake and would create
        # two columns that can silently disagree about which project owns a conversation.
        # `status` carries its own single-column index above.
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visitor_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Content retention. A retention field: enforced by the runtime, not the database.
    retention_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    # Lifecycle. Denormalised onto the conversation rather than reached through the session: the
    # inbox filters and sorts on it, and one join per row to derive "whose turn is it" is the wrong
    # shape for a list that is read constantly.
    status: Mapped[ConversationStatus] = mapped_column(
        SQLEnum(
            ConversationStatus,
            name="conversation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        # Every conversation is somewhere. A conversation that has not been classified yet is
        # PENDING rather than NULL, because an unanswered guest message is the one case that must
        # not be assumed handled.
        default=ConversationStatus.PENDING,
        nullable=False,
        index=True,
    )
    intent: Mapped[ConversationIntent | None] = mapped_column(
        SQLEnum(
            ConversationIntent,
            name="conversation_intent",
            values_callable=lambda e: [m.value for m in e],
        ),
        # Nullable, unlike status: intent is an inference and an honest "not classified yet" is more
        # useful than a default that silently becomes an eligibility decision for follow-ups.
        nullable=True,
    )
    #: STANDARD / HIGH. Drives escalation, and is a staff judgement as much as a classifier's.
    value: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Why the guest did not book. Set only when the status becomes LOST, and the reason is always
    #: one a person recorded or a guest stated - never one inferred from silence, which is what
    #: would make this field a guess dressed as a fact.
    lost_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: When a follow-up is next due, or NULL if none is scheduled. A schedule, not a status: the
    #: prototype's "follow-up running" was a phase, but chasing someone is an activity that can
    #: overlap any status.
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    session: Mapped["VisitorSession"] = relationship(
        "VisitorSession",
        back_populates="conversations",
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        # created_at alone is not a total order: two turns written in the same clock tick would
        # read back in either order. id breaks the tie, so the transcript is deterministic.
        order_by="[Message.created_at, Message.id]",
    )


class Message(BaseModel):
    """One turn in a conversation.

    Visitor-authored content, so it is untrusted data on read-back and must be fenced as data,
    never placed in a prompt's instruction region (FR-098).
    """

    __tablename__ = "messages"
    # Composite covers both "all messages in a conversation" and the ordered read; a separate
    # single-column index on conversation_id would be redundant. id is included to serve the
    # relationship's (created_at, id) ordering as a covering index.
    __table_args__ = (
        Index("ix_message_conversation_created", "conversation_id", "created_at", "id"),
        # One message per provider id per conversation. Partial so that rows with no provider id -
        # every assistant turn - are outside the constraint's scope.
        #
        # Note what the partial predicate does and does not buy. Under the default in both engines,
        # NULLs are distinct in a unique index, so a plain index would also let those rows through;
        # making it partial does not fix a present collision. What it buys is that the behaviour no
        # longer depends on that default, which Postgres 15+ can override per-type with
        # NULLS NOT DISTINCT. The claim is stated at its real strength: defensive, not load-bearing.
        Index(
            "uq_message_external_id",
            "conversation_id",
            "external_message_id",
            unique=True,
            sqlite_where=text("external_message_id IS NOT NULL"),
            postgresql_where=text("external_message_id IS NOT NULL"),
        ),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, name="message_role"),
        nullable=False,
    )
    direction: Mapped[MessageDirection] = mapped_column(
        SQLEnum(MessageDirection, name="message_direction"),
        nullable=False,
    )
    # Outbound lifecycle only; NULL on inbound rows, where it would be a fiction.
    status: Mapped[MessageStatus | None] = mapped_column(
        SQLEnum(MessageStatus, name="message_status"),
        nullable=True,
    )
    # The provider's own id for this message. Its purpose is idempotency: providers retry
    # webhooks, and a retried delivery must not write a second turn. The partial unique index
    # below enforces that in the database, because an application-level "have I seen this id?"
    # check races two concurrent retries of the same delivery - which is the normal case, not an
    # edge case, when a provider retries on a slow response.
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    # Citations for an assistant turn (B6): the documents the answer was grounded in. Empty for
    # visitor turns and for answers with no knowledge-base context.
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType,
        default=list,
        nullable=False,
    )
    # Which definition produced an assistant turn (B9), recorded per turn rather than per
    # conversation: a business can edit its instructions mid-conversation, and then the earlier
    # answers were produced by a definition that no longer exists. The engineering plane records
    # the same pair on `AgentRun`; this is the runtime's counterpart.
    #
    # `prompt_hash` is the hash of the instruction layer actually sent, because the version alone
    # does not identify it: tenant instructions change without a version bump.
    assistant_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )
