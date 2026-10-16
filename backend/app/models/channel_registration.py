"""A messaging address a project has claimed (ADR-004).

The counterpart to ``AllowedOrigin`` for channels that are not a browser. That table answers "may
this origin use this public key"; this one answers "which project does this phone number belong to",
which is the question a webhook arrives asking and the one there is no other way to answer.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from app.channels.base import Channel
from app.models.base import BaseModel

#: Phone numbers, handles and the like differ in length by provider and by era. Generous enough not
#: to truncate a real address, short enough that the column cannot be used as free text.
MAX_EXTERNAL_ID_LENGTH = 255


class ChannelRegistration(BaseModel):
    """One address, on one channel, **connected by the organisation**.

    An organisation connects as many numbers as it likes - a group with an Entebbe property and a
    Kampala one has two WhatsApp numbers - and then points individual projects at one of them
    (:class:`app.models.project_channel.ProjectChannel`). So ``project_id`` is **nullable**:
    claiming a number is an organisation-wide act in Settings, not something a project owns.

    ``external_identifier`` is stored in the canonical form of
    :func:`app.channels.base.normalize_external_id`, so registering ``+256772123456`` and receiving
    ``256772123456`` land on the same row. It is opaque and never parsed - a Telegram chat id is not a
    phone number and neither is a Slack user id.

    **One address is connected exactly once, organisation-wide.** That is a decision, not a
    simplification: a shared number has no way to decide which project an unknown guest wanted, so it
    would have to refuse first contact or route on something else - a keyword, or a link. Letting
    two organisations claim one number would mean building that, and quietly. If it is ever wanted
    it is a ``ChannelRoute`` table this deliberately does not have: a number per organisation, a
    route per project.

    The uniqueness spans ``is_active``: a deactivated registration still holds its address, so
    reactivation cannot collide with a number somebody else has since been given.

    **A connected number answers for nobody until a project selects it.** Routing reads through
    :class:`~app.models.project_channel.ProjectChannel`, so a number nobody has pointed a project at
    resolves to no tenant and the webhook refuses. Connecting a number must not by itself put it in
    front of guests.
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
        # Meta's numeric id, which is what the webhook actually carries. Partial, because only
        # WhatsApp has one and a plain unique index would forbid a second NULL-bearing row.
        Index(
            "uq_channel_registration_phone_number_id",
            "channel",
            "phone_number_id",
            unique=True,
            sqlite_where=text("phone_number_id IS NOT NULL"),
            postgresql_where=text("phone_number_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Nullable, and that is the point: an organisation connects numbers without every one of them
    #: being in front of a project. Which project answers on this number is
    #: ``ProjectChannel.registration_id``, not this column - keeping both would be two sources of
    #: truth for one routing decision, and the loser would silently be ignored.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
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
    #: Meta's numeric id for this business number, from the webhook's ``metadata`` block. This is
    #: what the adapter routes on and what the send endpoint needs as ``{PHONE_NUMBER_ID}``; the
    #: number above is what a tenant claims and a human reads, and Meta never sends it in the
    #: webhook. Nullable so a registration made before 0037 stays valid on its number alone.
    phone_number_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: A tenant's own system-user access token, from Embedded Signup, encrypted with
    #: :class:`app.core.secrets.SecretStore`. Takes precedence over the platform token; NULL means
    #: this number has not been onboarded individually and sends as the platform.
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
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