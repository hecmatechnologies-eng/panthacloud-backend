import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.integration_plan import IntegrationPlan
    from app.models.project import Project
    from app.models.repository_snapshot import RepositorySnapshot


class ExecutionPlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    READY = "READY"
    FAILED = "FAILED"


class ExecutionPlan(BaseModel):
    __tablename__ = "execution_plans"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ExecutionPlanStatus] = mapped_column(
        SQLEnum(
            ExecutionPlanStatus,
            name="execution_plan_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ExecutionPlanStatus.PLANNED,
        nullable=False,
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    required_credentials: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    prerequisites: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    approval_requirements: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    blocked_reasons: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="execution_plans",
    )
    snapshot: Mapped["RepositorySnapshot"] = relationship(
        "RepositorySnapshot",
        back_populates="execution_plans",
    )
    integration_plan: Mapped["IntegrationPlan"] = relationship(
        "IntegrationPlan",
        back_populates="execution_plans",
    )
