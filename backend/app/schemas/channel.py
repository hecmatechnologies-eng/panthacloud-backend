"""Request and response shapes for connected channel accounts and project selection.

**A stored access token is never returned.** ``ChannelAccountRead`` has no field for it, and that is
deliberate rather than an oversight: the endpoint that lists connected numbers is readable by
``CHANNEL_VIEW``, which a MEMBER has, and a schema is the one place that guarantees a secret cannot
be included by accident when somebody adds a field later. The frontend asks "is a token present?",
not "what is the token".

The write side is separate from the read side for the same reason. ``ChannelAccountCreate`` takes a
token and ``ChannelAccountRead`` does not have one, so the two can drift in what they expose without
a response ever learning to carry a secret.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.channels.base import Channel
from app.channels.base import normalize_external_id as _normalize
from app.models.channel_registration import MAX_EXTERNAL_ID_LENGTH


class ChannelAccountBase(BaseModel):
    """A connected account on one channel."""

    channel: Channel
    #: The address as the tenant knows it - a phone number for WhatsApp. Normalised before storage,
    #: so a hotel writing "+256 772 123 456" and Meta sending "256772123456" land on one row.
    external_identifier: str = Field(
        min_length=1,
        max_length=MAX_EXTERNAL_ID_LENGTH,
        description="The business address: a phone number for WhatsApp, a handle for Telegram.",
    )
    #: How a human recognises it. Free text on purpose - "+256 772 123 456" is the form a hotel
    #: prints on its signage and it need not round-trip through anything.
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("external_identifier")
    @classmethod
    def _canonicalise(cls, value: str, info) -> str:
        """Store the canonical form so registration and lookup agree.

        Two hand-written normalisers would eventually differ by a character and split one guest's
        history in two; going through the single function both sides call is what prevents it.
        """
        channel: Channel = info.data["channel"]
        canonical = _normalize(channel, value)
        if not canonical:
            raise ValueError("address is empty once normalised")
        return canonical


class ChannelAccountCreate(ChannelAccountBase):
    """Connect an account.

    Credentials are optional here because the two channels differ: a Telegram bot token is what
    makes a number usable at all, while WhatsApp's per-account access token arrives later with
    Embedded Signup and the app secret is platform-wide. Refusing a connection that has no token yet
    would block WhatsApp onboarding entirely; ``verified_at`` and ``has_access_token`` report the
    difference instead of hiding it.
    """

    #: Meta's numeric id for the business number. Required for WhatsApp, because it is both what
    #: inbound routing prefers and what the send endpoint needs as ``{PHONE_NUMBER_ID}``.
    phone_number_id: str | None = Field(default=None, max_length=255)
    #: A tenant's own system-user token, from Embedded Signup. Encrypted before storage through the
    #: existing SecretStore; never returned.
    access_token: str | None = Field(default=None, max_length=4096)


class ChannelAccountRead(BaseModel):
    """A connected account. Carries no secret, by design."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: Channel
    external_identifier: str
    display_name: str | None
    phone_number_id: str | None
    is_active: bool
    verified_at: datetime | None
    #: Whether this account has its own token, so the UI can say "needs credentials" instead of
    #: guessing from the absence of a field.
    has_access_token: bool
    #: The project currently answering on this account, if any. Null for a connected number nobody
    #: has selected - which is a normal state, not an error, and matters because such a number
    #: routes to nobody.
    selected_by_project_id: uuid.UUID | None
    selected_by_project_name: str | None


class ChannelAccountUpdate(BaseModel):
    """Retire or restore an account.

    Deactivation rather than deletion: the row still holds the address, so the number cannot be
    handed to another tenant while it sits around, and the history attached to it survives.
    """

    is_active: bool


class ProjectChannelRead(BaseModel):
    """One project's choice of account for one channel."""

    model_config = ConfigDict(from_attributes=True)

    channel: Channel
    channel_registration_id: uuid.UUID
    external_identifier: str
    display_name: str | None
    is_active: bool
    has_access_token: bool
    selected_at: datetime


class ProjectChannelSet(BaseModel):
    """Point a project at a connected account."""

    channel_registration_id: uuid.UUID


__all__ = [
    "ChannelAccountCreate",
    "ChannelAccountRead",
    "ChannelAccountUpdate",
    "ProjectChannelRead",
    "ProjectChannelSet",
]