"""Which connected channel account a project's assistant answers on.

The join between the two things the organisation-wide model needs to keep apart:

- :class:`~app.models.channel_registration.ChannelRegistration` - a number the organisation has
  **connected**. Settings-level, many per organisation, holds the credentials.
- ``ProjectChannel`` - the **one** of those a given project's assistant uses. Project-level, one per
  project per channel.

Keeping these separate is what lets a group connect an Entebbe number and a Kampala one once and then
decide, per project, which the assistant speaks on. A single column on ``Project`` would have meant
one nullable column per channel and no way to say "this account is not in use anywhere".

**Both uniqueness constraints here are load-bearing, and one is forced rather than chosen.**

``(project_id, channel)``
    One account per project per channel. This is the product rule: a project's assistant answers on
    one number, and offering a second would leave "where do replies go?" unanswerable.

``(channel, registration_id)``
    An account serves at most one project. **This one is not a preference - it is forced by
    inbound routing.** A WhatsApp webhook names the *business number* and nothing else; it does not
    say which project asked. If two projects shared one number, the resolver would have two correct
    answers and no field to choose between them, so whichever it picked would be an arbitrary
    coin-flip silently stealing the other project's guests.

    Making it unrepresentable rather than merely discouraged is the whole reason this table exists
    in the shape it does. If per-project routing on a shared number is ever wanted, it needs a
    routing key in the payload - a keyword, or a link - and this constraint becomes the thing to
    relax.

``ON DELETE CASCADE`` on both keys: deleting a project removes its selection, and deleting a
registration removes any selection pointing at it, so an account cannot outlive the credential that
makes it usable and leave routing pointing at a row that can never be read.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from app.channels.base import Channel
from app.models.base import BaseModel


class ProjectChannel(BaseModel):
    """A project's choice of connected account for one channel."""

    __tablename__ = "project_channels"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "channel",
            name="uq_project_channel_project",
        ),
        UniqueConstraint(
            "channel",
            "channel_registration_id",
            name="uq_project_channel_registration",
        ),
        # Reading the project's selections for the settings page and for the resolver's join.
        Index("ix_project_channel_project", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[Channel] = mapped_column(
        SQLEnum(Channel, name="session_channel", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    #: The connected account this project answers on. Cascaded: a registration that has been
    #: deleted cannot be routed to.
    channel_registration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channel_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: When the choice was last made. Not decoration: "which number was live when this conversation
    #: started" is the first question anyone asks after a hotel reports guests reaching the wrong
    #: desk, and this is what answers it.
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


__all__ = ["ProjectChannel"]