"""user accounts and oauth support

Revision ID: 0023_user_accounts_oauth
Revises: 0022_integration_installation
Create Date: 2026-09-14 18:25:00.000000

Step: Decouple user identity from local credentials to support OAuth (GitHub, Google).
- Make users.hashed_password nullable
- Add users.avatar_url
- Create accounts table with delegated encrypted token storage
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023_user_accounts_oauth"
down_revision: str | None = "0022_integration_installation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Make hashed_password nullable for OAuth users
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    # 2. Add avatar_url to users table
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
    )

    # 3. Create accounts table
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("scopes", sa.String(length=255), nullable=True),
        sa.Column("profile_metadata", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_account_id", name="uq_accounts_provider_account_id"),
    )
    op.create_index(op.f("ix_accounts_user_id"), "accounts", ["user_id"], unique=False)
    op.create_index(op.f("ix_accounts_provider"), "accounts", ["provider"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_accounts_provider"), table_name="accounts")
    op.drop_index(op.f("ix_accounts_user_id"), table_name="accounts")
    op.drop_table("accounts")
    op.drop_column("users", "avatar_url")
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
