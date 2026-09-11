import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.repository import Repository


class IntegrationProvider(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    EXTERNAL_API = "external_api"
    WEBHOOK = "webhook"


class IntegrationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class Integration(BaseModel):
    __tablename__ = "integrations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        SQLEnum(
            IntegrationProvider,
            name="integration_provider",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        SQLEnum(
            IntegrationStatus,
            name="integration_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=IntegrationStatus.PENDING,
        nullable=False,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    encrypted_secrets: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="integrations",
    )
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository",
        back_populates="integration",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_integration_project_name"),
    )
