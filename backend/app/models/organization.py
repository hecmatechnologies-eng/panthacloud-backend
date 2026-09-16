from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.membership import Membership
    from app.models.organization_model_settings import OrganizationModelSettings
    from app.models.project import Project


class Organization(BaseModel):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    memberships: Mapped[list["Membership"]] = relationship(
        "Membership",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    # ORM cascade, not just the FK's `ondelete`: SQLite runs with the foreign_keys pragma off, so
    # the database clause is inert there and this is what actually deletes the row.
    model_settings: Mapped["OrganizationModelSettings | None"] = relationship(
        "OrganizationModelSettings",
        back_populates="organization",
        cascade="all, delete-orphan",
        uselist=False,
    )
