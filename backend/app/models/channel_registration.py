"""A messaging address a project has claimed (ADR-004).

The counterpart to ``AllowedOrigin`` for channels that are not a browser. That table answers "may
this origin use this public key"; this one answers "which project does this phone number belong to",
which is the question a webhook arrives asking and the one there is no other way to answer.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from app.channels.base import Channel
from app.models.base import BaseModel

#: Phone numbers, handles and the like differ in length by provider and by era. Generous enough not
#: to truncate a real address, short enough that the column cannot be used as free text.
MAX_EXTERNAL_ID_LENGTH = 255


class ChannelRegistration(BaseModel):
    """One address, on one channel, belonging to one project.

    ``external_identifier`` is stored in the canonical form of
    :func:`app.channels.base.normalize_external_id`, so registering ``+256772123456`` and receiving
    ``256772123456`` land on the same row. It is opaque and never parsed - a Telegram chat id is not
    a phone number and neither is a Slack user id.

    **One address claims exactly one project.** That is a decision, not a simplification: a shared
    number has no way to decide which project an unknown guest wanted, so it would have to refuse
    first contact or route on something else - a keyword, or a link. Letting several projects claim
    the same number would mean building that, and quietly. If it is ever wanted, it is the
    ``ChannelRoute`` table this deliberately does not have: a number per organisation, a route per
    project.

    The uniqueness spans ``is_active``: a deactivated registration still holds its address, so
    reactivation cannot collide with a number somebody else has since been given.
    """

    __tablename__ = "channel_registrations"
    __table_args__ = (
        # The identity of a registered address. Global across organisations on purpose - two tenants
        # claiming one number is a conflict to be reported, not a silent last-writer-wins.
        Index(
            "uq_channel_registration_address",
            "channel",
            "external_identifier",
            unique=True,
        ),
        # Listing a project's channels, which is how the Studio will show them and how the tests
        # scope. Separate from the unique index because the leading column differs.
        Index("ix_channel_registration_project_channel", "project_id", "channel"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[Channel] = mapped_column(
        # The same enum as ``visitor_sessions.channel``, so a session's channel and the registration
        # that routed it cannot be spelled differently. Renaming a value is still a migration.
        SQLEnum(Channel, name="session_channel", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    external_identifier: Mapped[str] = mapped_column(
        String(MAX_EXTERNAL_ID_LENGTH),
        nullable=False,
    )
    #: How a human recognises this address - "+256 772 123 456", not "256772123456".
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: An inactive registration still holds its address but answers no traffic, which is how a
    #: number is retired without giving it away and without dropping its history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Set once the provider has proved control of the address. Null means a tenant has claimed the
    #: number but nobody has yet received a verification challenge on it.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Who claimed it, for the audit trail. Null when the row was seeded directly or provisioned by
    #: the platform rather than by a person.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )