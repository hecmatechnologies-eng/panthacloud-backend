"""Read models for the staff inbox (ADR-004, K6).

Deliberately flatter than the ORM. The list row exists to render one table, and a response that
mirrors five joined tables would push the joining into the frontend - where it cannot be paginated,
cannot be indexed, and would have to be redone for the detail view anyway.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.channels.base import Channel
from app.models.conversation import (
    ConversationIntent,
    ConversationStatus,
    MessageRole,
    MessageStatus,
)


class ConversationSummary(BaseModel):
    """One row of the Guest session logs table.

    ``project_name`` is here because the list is reached from the organisation's side nav and is not
    filtered to one property: a group operator with three hotels sees "Guest A" three times, and
    without the property the table reads as a bug rather than as three hotels.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    channel: Channel
    #: The guest's address on that channel. Opaque and never parsed - a Telegram chat id is not a
    #: phone number. Null for a widget session, which has no external identity.
    external_id: str | None
    status: ConversationStatus
    intent: ConversationIntent | None
    value: str | None
    lost_reason: str | None
    next_follow_up_at: datetime | None
    message_count: int
    #: Null until the conversation has at least one message. The list sorts on ``created_at`` rather
    #: than this - see the endpoint docstring for why, and what would change it.
    last_message_at: datetime | None
    created_at: datetime


class ConversationMessage(BaseModel):
    """One turn in the transcript.

    ``direction`` and ``status`` are separate because they answer different questions: which way it
    went, and what happened to it afterwards. An inbound guest message has no status - a guest's
    message was not "sent", it arrived - while an outbound reply may be ``drafted`` and never have
    reached anyone.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    direction: str
    status: MessageStatus | None
    content: str
    #: The documents this reply was built from. Empty on a refusal, which is the point: there is
    #: nothing to cite when nothing was retrieved.
    citations: list[dict[str, Any]] = []
    #: The provider's own id for an outbound message. Null for the widget, which has no provider.
    external_message_id: str | None = None
    assistant_version: str | None = None
    prompt_hash: str | None = None
    created_at: datetime


class ConversationDetail(BaseModel):
    """A conversation and its full transcript."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    channel: Channel
    external_id: str | None
    status: ConversationStatus
    intent: ConversationIntent | None
    value: str | None
    lost_reason: str | None
    next_follow_up_at: datetime | None
    created_at: datetime
    messages: list[ConversationMessage]