"""How a project's mail looks (and will look on every other channel).

A guest assistant that answers *"what time is check-out?"* with an unbranded wall of plain text
reads as a bot that found the email address somewhere. That is a real problem for a business, and it
is separate from whether the message reaches the inbox at all - this table has no bearing on spam
placement, because that is decided by the sending pool's reputation rather than by what the message
says. Recorded here so the two are not confused later.

**One row per project, and optional.** Absence is a legitimate state, not a half-built one: a project
with no branding gets a plain, unstyled message with no footer, which is exactly what a brand-new
tenant should send until they have told us who they are. Hardcoding a default hotel would put one
tenant's identity in the platform's code, where the next tenant would inherit it.

Fields are deliberately flat strings rather than a nested document. These are edited by staff in a
form, validated individually, and rendered into an email that must look right in Outlook as well as
Gmail - none of which is made easier by genericity.

``accent_colour``
    Kept to one brand colour rather than a palette. Email clients strip ``<style>`` blocks and ignore
    most CSS, so what survives is inline attributes on table cells and text; a whole design system
    would be fiction. ``#RRGGBB`` only, validated, because anything else silently renders as black.

``social_links``
    A JSON object of platform to URL. A list would need its own table and an ordering column for four
    entries that are only ever read together. Restricted to a known set of platform names so the
    renderer can pick a glyph, and so a tenant cannot inject arbitrary markup through a key.

``footer_note``
    Why the guest is receiving this. Not decoration: unsolicited-looking mail scores worse than mail
    that says plainly "you wrote to us, here is our address, here is how to stop". It is also the
    only place a guest learns the hotel's postal address and telephone number, which several
    jurisdictions require unsolicited commercial mail to carry.
"""

import uuid

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from app.models.base import BaseModel

#: Social platforms the renderer knows how to label. Closed on purpose - see ``social_links``.
SOCIAL_PLATFORMS = ("facebook", "instagram", "x", "linkedin", "youtube", "tiktok")

#: Upper bound on each free-text field. Generous for a real business, short enough that the row
#: cannot be used as a document store.
MAX_NAME_LENGTH = 160
MAX_URL_LENGTH = 500
MAX_PHONE_LENGTH = 40
MAX_COLOUR_LENGTH = 7


class ProjectBranding(BaseModel):
    """One project's outward identity, as shown to guests on every channel."""

    __tablename__ = "project_branding"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    business_name: Mapped[str] = mapped_column(String(MAX_NAME_LENGTH), nullable=False)
    #: Short line under the name. Optional: plenty of businesses have nothing to add.
    tagline: Mapped[str | None] = mapped_column(String(MAX_NAME_LENGTH), nullable=True)
    #: Hosted elsewhere (R2, the tenant's own CDN). Not uploaded here - an image upload path would
    #: need storage lifecycle, size limits and virus scanning, and none of that is needed to make a
    #: header look right. A tenant with no logo gets initials, which is usually fine.
    logo_url: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH), nullable=True)
    #: `#RRGGBB`. One colour, deliberately - see the module docstring.
    accent_colour: Mapped[str | None] = mapped_column(String(MAX_COLOUR_LENGTH), nullable=True)
    postal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(MAX_PHONE_LENGTH), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH), nullable=True)
    website: Mapped[str | None] = mapped_column(String(MAX_URL_LENGTH), nullable=True)
    #: Platform name to URL. See ``SOCIAL_PLATFORMS`` for why this is an object and not a list.
    social_links: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    #: Why the guest is receiving this, and how to stop. Rendered above the contact details.
    footer_note: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["MAX_COLOUR_LENGTH", "MAX_NAME_LENGTH", "MAX_URL_LENGTH", "SOCIAL_PLATFORMS", "ProjectBranding"]