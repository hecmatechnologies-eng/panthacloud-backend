"""A persisted WebsiteAnalyst result (step C10).

One row per analysis of a website integration, keyed to the commit SHA it was derived from. This is
the thin project memory (FR-058–062): derived data, fingerprinted by commit, so a re-run on an
unchanged repository can be recognised as current.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.website_integration import WebsiteIntegration


class WebsiteAnalysis(BaseModel):
    __tablename__ = "website_analyses"
    __table_args__ = (
        Index("ix_website_analyses_integration_created", "integration_id", "created_at"),
    )

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The pinned revision this analysis was derived from; a different HEAD makes it stale.
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    framework_skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    router: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    package_manager: Mapped[str | None] = mapped_column(String(50), nullable=True)
    build_command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_points: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    integration_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    design_tokens: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    protected_paths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    unsupported_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The run that produced this analysis, for audit (SET NULL: the analysis outlives the run).
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    integration: Mapped["WebsiteIntegration"] = relationship(
        "WebsiteIntegration", back_populates="analyses"
    )
