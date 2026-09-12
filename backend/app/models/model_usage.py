"""Model usage ledger (FR-073, FR-075).

One row per model call, attributed to an organization, so per-run and per-conversation cost are
first-class numbers rather than an inference. Append-only: nothing updates or deletes a row except
the deletion of the owning organization.

The subject links are deliberately ``SET NULL`` rather than ``CASCADE``: deleting a project or a
conversation must not erase the record that a call was paid for. Only deleting the organization —
which purges the tenant — removes its usage.
"""

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UUID

from app.models.base import BaseModel


class ModelUsage(BaseModel):
    __tablename__ = "model_usage"
    __table_args__ = (
        # Serves the per-organization budget query and the ledger's time ordering; the single
        # organization_id index would be redundant with this.
        Index("ix_model_usage_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_integrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal(0)
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
