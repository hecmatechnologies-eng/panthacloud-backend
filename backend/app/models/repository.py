import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.integration import Integration
    from app.models.project import Project
    from app.models.repository_snapshot import RepositorySnapshot


class RepositoryProvider(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class RepositoryStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class Repository(BaseModel):
    __tablename__ = "repositories"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[RepositoryProvider] = mapped_column(
        SQLEnum(
            RepositoryProvider,
            name="repository_provider",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    default_branch: Mapped[str] = mapped_column(
        String(255),
        default="main",
        nullable=False,
    )
    url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    status: Mapped[RepositoryStatus] = mapped_column(
        SQLEnum(
            RepositoryStatus,
            name="repository_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=RepositoryStatus.PENDING,
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
        back_populates="repositories",
    )
    integration: Mapped["Integration"] = relationship(
        "Integration",
        back_populates="repositories",
    )
    snapshots: Mapped[list["RepositorySnapshot"]] = relationship(
        "RepositorySnapshot",
        back_populates="repository",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("integration_id", "external_id", name="uq_repository_integration_external_id"),
    )
