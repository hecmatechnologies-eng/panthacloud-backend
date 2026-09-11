import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.integration_plan import IntegrationPlan
    from app.models.repository_snapshot import RepositorySnapshot


class AdapterStatus(str, enum.Enum):
    PENDING = "PENDING"
    PLANNED = "PLANNED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    READY = "READY"
    FAILED = "FAILED"


class AdapterType(str, enum.Enum):
    DATABASE = "DATABASE"
    CACHE = "CACHE"
    PAYMENT = "PAYMENT"
    STORAGE = "STORAGE"
    HTTP_API = "HTTP_API"
    WEBHOOK = "WEBHOOK"
    VERSION_CONTROL = "VERSION_CONTROL"
    AUTHENTICATION = "AUTHENTICATION"
    MESSAGE_BROKER = "MESSAGE_BROKER"
    UNKNOWN = "UNKNOWN"


class IntegrationAdapter(BaseModel):
    __tablename__ = "integration_adapters"

    integration_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    adapter_type: Mapped[AdapterType] = mapped_column(
        SQLEnum(
            AdapterType,
            name="adapter_type",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    provider: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    status: Mapped[AdapterStatus] = mapped_column(
        SQLEnum(
            AdapterStatus,
            name="adapter_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=AdapterStatus.PLANNED,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    required_credentials: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    operations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    prerequisites: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    constraints: Mapped[list[str]] = mapped_column(
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

    integration_plan: Mapped["IntegrationPlan"] = relationship(
        "IntegrationPlan",
        back_populates="adapters",
    )
    snapshot: Mapped["RepositorySnapshot"] = relationship(
        "RepositorySnapshot",
        back_populates="integration_adapters",
    )
