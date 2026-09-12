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

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID

from app.core.origins import MAX_ORIGIN_LENGTH
from app.models.base import BaseModel
from app.models.knowledge import JSONType

if TYPE_CHECKING:
    from app.models.website_integration import WebsiteIntegration


class MessageRole(str, enum.Enum):
    VISITOR = "VISITOR"
    ASSISTANT = "ASSISTANT"


class VisitorSession(BaseModel):
    """One visitor's browser session on a website integration (FR-108, FR-113).

    Created only after the tenant resolver has bound a request to an integration. The session is
    the scope for conversation memory and rate limiting; ``expires_at`` is its TTL.
    """

    __tablename__ = "visitor_sessions"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The canonical origin the session was created from, as returned by the resolver. Stored so a
    # later turn can be bound to the origin it began under.
    origin: Mapped[str] = mapped_column(
        String(MAX_ORIGIN_LENGTH),
        nullable=False,
    )
    # Session validity TTL. A retention field: enforced by the runtime, not the database.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    integration: Mapped["WebsiteIntegration"] = relationship(
        "WebsiteIntegration",
        back_populates="visitor_sessions",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Conversation.created_at",
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

    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )
