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

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
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
        # Partial, on `external_id IS NOT NULL`, because that is what excludes widget rows. A plain
        # unique index would rely on NULLs being distinct, which is the default in Postgres and
        # SQLite but is configurable (`NULLS NOT DISTINCT`) and therefore an assumption rather than
        # a guarantee. The partial predicate states the intent instead: a widget session has no
        # external id and does not participate in this constraint at all.
        #
        # Widget rows therefore keep no uniqueness guarantee of their own - deliberately the status
        # quo, where they are found by a client-supplied id rather than looked up by identity.
        # Enforcing it per origin would break a visitor who clears browser storage mid-visit.
        Index(
            "uq_visitor_session_channel_identity",
            "project_id",
            "channel",
            "external_id",
            "thread_id",
            unique=True,
            sqlite_where=text("external_id IS NOT NULL"),
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )


class Conversation(BaseModel):
    """A visitor chat thread (FR-113, FR-119).

    Retention is deliberately its own timestamp, independent of the session TTL: a session can
    lapse while the conversation's content is still within its retention window (FR-056).
    """

    __tablename__ = "conversations"

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
