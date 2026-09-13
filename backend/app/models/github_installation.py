"""A GitHub App installation linked to an organization (step E).

One row per installation the tenant has authorized. The installation id is GitHub's; the credential
is never stored — a short-lived installation access token is minted from the app private key on
demand (`app/services/integration/github_app.py`).
"""

import uuid

from sqlalchemy import UUID, BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class GitHubInstallation(BaseModel):
    __tablename__ = "github_installations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # GitHub's installation id. Unique: one installation belongs to exactly one account and is
    # linked to exactly one tenant.
    installation_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
    )
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False, default="User")
    # "all" or "selected": which repositories the installer granted.
    repository_selection: Mapped[str] = mapped_column(
        String(20), nullable=False, default="selected"
    )
