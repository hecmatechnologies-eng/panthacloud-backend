"""The model an organization's assistants run on (FR-072, FR-075).

One row per organization, and only for organizations that have chosen one: **the absence of a row is
the deployment default**. A new organization is therefore configured by doing nothing, and the
platform keeps a single place to change what everyone starts on.

Deliberately narrow. A model id is not a provider, a base URL or a credential — each of those
arrives with the slice that needs it, and a table that guessed at them now would hold columns
nothing reads. The id must be one of ``settings.MODEL_ALLOWED_IDS``: enforced when it is written
(the API refuses anything else) and again when it is used (the gateway's allow-list, which is the
one check no caller can bypass).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization


class OrganizationModelSettings(BaseModel):
    __tablename__ = "organization_model_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="model_settings",
    )
