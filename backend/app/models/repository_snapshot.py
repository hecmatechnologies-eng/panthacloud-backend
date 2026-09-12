import datetime
import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.discovery import DiscoveryRun
    from app.models.repository import Repository


class SnapshotStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACQUIRING = "ACQUIRING"
    READY = "READY"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


class RepositorySnapshot(BaseModel):
    __tablename__ = "repository_snapshots"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    status: Mapped[SnapshotStatus] = mapped_column(
        SQLEnum(
            SnapshotStatus,
            name="snapshot_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=SnapshotStatus.PENDING,
        nullable=False,
    )
    workspace_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    acquired_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="snapshots",
    )
    discovery_runs: Mapped[list["DiscoveryRun"]] = relationship(
        "DiscoveryRun",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )
