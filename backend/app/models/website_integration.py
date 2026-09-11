import enum
import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.allowed_origin import AllowedOrigin
    from app.models.project import Project

PUBLIC_KEY_PREFIX = "fussion_pk_"


def generate_public_key() -> str:
    """A widget's public client key (FR-107). Not a secret: it ships in the customer's page.

    192 random bits, so an unknown key cannot be guessed; the prefix tells it apart from a
    credential at a glance and to secret scanners.
    """
    return PUBLIC_KEY_PREFIX + secrets.token_urlsafe(24)


class WebsiteIntegrationStatus(str, enum.Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTED = "CONNECTED"
    PLANNING = "PLANNING"
    SANDBOX_READY = "SANDBOX_READY"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    READY_FOR_PR = "READY_FOR_PR"
    PR_CREATED = "PR_CREATED"
    FAILED = "FAILED"


class IntegrationRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    READY_FOR_PR = "READY_FOR_PR"
    PR_CREATED = "PR_CREATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WebsiteFramework(str, enum.Enum):
    REACT_NEXTJS = "REACT_NEXTJS"
    GENERIC_HTML = "GENERIC_HTML"


class WebsiteIntegration(BaseModel):
    __tablename__ = "website_integrations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        default="github",
        nullable=False,
    )
    repository_owner: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    repository_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    default_branch: Mapped[str] = mapped_column(
        String(100),
        default="main",
        nullable=False,
    )
    integration_branch: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )
    framework: Mapped[WebsiteFramework] = mapped_column(
        SQLEnum(WebsiteFramework, name="website_framework"),
        default=WebsiteFramework.REACT_NEXTJS,
        nullable=False,
    )
    website_root_dir: Mapped[str] = mapped_column(
        String(255),
        default="/",
        nullable=False,
    )
    widget_target_path: Mapped[str] = mapped_column(
        String(255),
        default="app/layout.tsx",
        nullable=False,
    )
    status: Mapped[WebsiteIntegrationStatus] = mapped_column(
        SQLEnum(WebsiteIntegrationStatus, name="website_integration_status"),
        default=WebsiteIntegrationStatus.NOT_CONNECTED,
        nullable=False,
    )
    encrypted_secrets: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Server-issued only; no create or update schema accepts it.
    public_key: Mapped[str] = mapped_column(
        String(64),
        default=generate_public_key,
        nullable=False,
        unique=True,
        index=True,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="website_integration",
    )
    runs: Mapped[list["IntegrationRun"]] = relationship(
        "IntegrationRun",
        back_populates="website_integration",
        cascade="all, delete-orphan",
        order_by="IntegrationRun.started_at.desc()",
    )
    allowed_origins: Mapped[list["AllowedOrigin"]] = relationship(
        "AllowedOrigin",
        back_populates="website_integration",
        cascade="all, delete-orphan",
        order_by="AllowedOrigin.created_at",
    )


class IntegrationRun(BaseModel):
    __tablename__ = "integration_runs"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("website_integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[IntegrationRunStatus] = mapped_column(
        SQLEnum(IntegrationRunStatus, name="integration_run_status"),
        default=IntegrationRunStatus.PENDING,
        nullable=False,
    )
    branch_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    pull_request_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    pull_request_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    sandbox_ref: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    plan_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    generated_files_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    modified_files_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    website_integration: Mapped["WebsiteIntegration"] = relationship(
        "WebsiteIntegration",
        back_populates="runs",
    )
