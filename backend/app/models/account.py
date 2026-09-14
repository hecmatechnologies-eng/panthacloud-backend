import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Account(BaseModel):
    """
    Tracks external authentication provider identities (OAuth / SSO).
    Separates user profile identity from auth mechanisms and credentials.
    """

    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    provider_account_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    # Delegated credentials encrypted at rest with Fernet / AES-256 via SecretStore
    encrypted_access_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    scopes: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # JSONB on PostgreSQL, JSON fallback for SQLite test environments
    profile_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="accounts",
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_accounts_provider_account_id"),
    )
