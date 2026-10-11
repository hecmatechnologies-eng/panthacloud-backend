"""Agent run persistence (FR-051, FR-052, FR-089, FR-090).

One ``AgentRun`` per agent execution, with an ordered ``AgentToolCall`` log beneath it. Together
they are the run's history — replayable, reproducible, and the substrate the harness resumes from.
Attributed to an organization and purged with it (FR-062).
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel


class AgentRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FailureClass(str, enum.Enum):
    """FR-100: every failure is classified, and the class decides the response."""

    RETRYABLE = "RETRYABLE"
    TERMINAL = "TERMINAL"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    REFUSED = "REFUSED"


class AgentRun(BaseModel):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        SQLEnum(AgentRunStatus, name="agent_run_status"),
        default=AgentRunStatus.PENDING,
        nullable=False,
    )
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Reproducibility (FR-089): what produced this run, not just what it concluded.
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version_reported: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), default=Decimal(0), nullable=False
    )
    # The trusted context this run was built from, snapshotted for audit.
    execution_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    failure_class: Mapped[FailureClass | None] = mapped_column(
        SQLEnum(FailureClass, name="agent_failure_class"),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tool_calls: Mapped[list["AgentToolCall"]] = relationship(
        "AgentToolCall",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentToolCall.sequence",
    )


class AgentToolCall(BaseModel):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "sequence", name="uq_agent_tool_call_run_sequence"),
    )

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Sensitive values are referenced or redacted by the tool gateway, never stored raw (FR-069).
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Approval provenance, recorded only for write tools. ASI09 asks for an immutable record of
    # what was authorised, not just what ran; without these the write tool call is
    # indistinguishable from one the agent performed on its own authority.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approver_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approved_plan_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="tool_calls")
