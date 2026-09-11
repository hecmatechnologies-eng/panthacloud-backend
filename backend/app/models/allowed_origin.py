import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID

from app.core.origins import MAX_ORIGIN_LENGTH
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.website_integration import WebsiteIntegration


class AllowedOrigin(BaseModel):
    """A site origin registered for a website integration's public key (FR-107).

    ``origin`` is stored in the canonical form produced by ``app.core.origins.normalize_origin``. The same origin may be registered
    under different integrations: tenancy comes from the public key, the origin only validates it.
    """

    __tablename__ = "allowed_origins"
    __table_args__ = (
        UniqueConstraint("integration_id", "origin", name="uq_allowed_origin_integration_origin"),
    )

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    origin: Mapped[str] = mapped_column(
        # One bound, shared with the validator, so the two cannot drift apart.
        String(MAX_ORIGIN_LENGTH),
        nullable=False,
    )

    website_integration: Mapped["WebsiteIntegration"] = relationship(
        "WebsiteIntegration",
        back_populates="allowed_origins",
    )
