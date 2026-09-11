import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.contract import ApiContract
    from app.models.execution_plan import ExecutionPlan
    from app.models.integration_adapter import IntegrationAdapter
    from app.models.project import Project
    from app.models.repository_snapshot import RepositorySnapshot


class IntegrationPlanStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IntegrationPlan(BaseModel):
    __tablename__ = "integration_plans"

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
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    status: Mapped[IntegrationPlanStatus] = mapped_column(
        SQLEnum(
            IntegrationPlanStatus,
            name="integration_plan_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=IntegrationPlanStatus.PENDING,
        nullable=False,
    )
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    required_credentials: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    unresolved_questions: Mapped[list[dict[str, Any]]] = mapped_column(
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
        back_populates="integration_plans",
    )
    snapshot: Mapped["RepositorySnapshot"] = relationship(
        "RepositorySnapshot",
        back_populates="integration_plans",
    )
    contract: Mapped["ApiContract | None"] = relationship(
        "ApiContract",
        back_populates="integration_plans",
    )
    adapters: Mapped[list["IntegrationAdapter"]] = relationship(
        "IntegrationAdapter",
        back_populates="integration_plan",
        cascade="all, delete-orphan",
    )
    execution_plans: Mapped[list["ExecutionPlan"]] = relationship(
        "ExecutionPlan",
        back_populates="integration_plan",
        cascade="all, delete-orphan",
    )
