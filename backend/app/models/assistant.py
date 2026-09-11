import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UUID

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.project import Project


class AssistantPosition(str, enum.Enum):
    BOTTOM_RIGHT = "BOTTOM_RIGHT"
    BOTTOM_LEFT = "BOTTOM_LEFT"


class Assistant(BaseModel):
    __tablename__ = "assistants"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        default="Fussion Assistant",
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    welcome_message: Mapped[str] = mapped_column(
        Text,
        default="Hi! How can I help you today?",
        nullable=False,
    )
    system_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    brand_color: Mapped[str] = mapped_column(
        String(20),
        default="#6366F1",
        nullable=False,
    )
    text_color: Mapped[str] = mapped_column(
        String(20),
        default="#FFFFFF",
        nullable=False,
    )
    position: Mapped[AssistantPosition] = mapped_column(
        SQLEnum(AssistantPosition, name="assistant_position"),
        default=AssistantPosition.BOTTOM_RIGHT,
        nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    starter_prompt: Mapped[str | None] = mapped_column(
        Text,
        default="What can you tell me about your products?",
        nullable=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="assistant",
    )
