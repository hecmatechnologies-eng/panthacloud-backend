import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.assistant import Assistant
    from app.models.execution_plan import ExecutionPlan
    from app.models.integration import Integration
    from app.models.integration_plan import IntegrationPlan
    from app.models.knowledge import KnowledgeBase
    from app.models.organization import Organization
    from app.models.repository import Repository
    from app.models.website_integration import WebsiteIntegration


class Project(BaseModel):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="projects",
    )
    integrations: Mapped[list["Integration"]] = relationship(
        "Integration",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    integration_plans: Mapped[list["IntegrationPlan"]] = relationship(
        "IntegrationPlan",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    execution_plans: Mapped[list["ExecutionPlan"]] = relationship(
        "ExecutionPlan",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship(
        "KnowledgeBase",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    assistant: Mapped["Assistant | None"] = relationship(
        "Assistant",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    website_integration: Mapped["WebsiteIntegration | None"] = relationship(
        "WebsiteIntegration",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_project_organization_slug"),
    )

