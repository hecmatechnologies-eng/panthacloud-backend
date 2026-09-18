"""allowed_origins guardrails and integration status expansion

Revision ID: 0029_allowed_origins_guardrails_and_integration_status
Revises: 0028_user_token_version
Create Date: 2026-09-18 07:00:00.000000

Adds is_verified, source, and last_seen_at columns to allowed_origins table.
Expands website_integration_status enum with PR_MERGED and DEPLOYED.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029_allowed_origins_guardrails_and_integration_status"
down_revision: str | None = "0028_user_token_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE website_integration_status ADD VALUE IF NOT EXISTS 'PR_MERGED'"
        )
        op.execute(
            "ALTER TYPE website_integration_status ADD VALUE IF NOT EXISTS 'DEPLOYED'"
        )

    with op.batch_alter_table("allowed_origins") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(length=50),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_seen_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("allowed_origins") as batch_op:
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("source")
        batch_op.drop_column("is_verified")
