"""website integration public key and allowed origins

Revision ID: 0012_public_key_allowed_origins
Revises: 0011_website_integrations
Create Date: 2026-09-11 21:10:00.000000

"""
import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_public_key_allowed_origins"
down_revision: str | None = "0011_website_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Deliberately inlined rather than imported from app.models: a migration must keep producing the
# same thing this revision produced, whatever the application later does.
PUBLIC_KEY_PREFIX = "fussion_pk_"


def upgrade() -> None:
    op.add_column(
        "website_integrations",
        sa.Column("public_key", sa.String(length=64), nullable=True),
    )

    # Backfill: every existing integration gets its own key before the column becomes NOT NULL.
    # The id is read and bound back as the raw stored value, with no type coercion in between, so
    # this does not depend on how a UUID happens to be rendered by the dialect.
    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM website_integrations")).fetchall()]
    for integration_id in ids:
        bind.execute(
            sa.text("UPDATE website_integrations SET public_key = :key WHERE id = :id"),
            {"key": PUBLIC_KEY_PREFIX + secrets.token_urlsafe(24), "id": integration_id},
        )

    with op.batch_alter_table("website_integrations") as batch_op:
        batch_op.alter_column("public_key", existing_type=sa.String(length=64), nullable=False)
    op.create_index(
        op.f("ix_website_integrations_public_key"),
        "website_integrations",
        ["public_key"],
        unique=True,
    )

    op.create_table(
        "allowed_origins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["website_integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "origin", name="uq_allowed_origin_integration_origin"),
    )
    op.create_index(
        op.f("ix_allowed_origins_integration_id"),
        "allowed_origins",
        ["integration_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_allowed_origins_integration_id"), table_name="allowed_origins")
    op.drop_table("allowed_origins")

    op.drop_index(op.f("ix_website_integrations_public_key"), table_name="website_integrations")
    with op.batch_alter_table("website_integrations") as batch_op:
        batch_op.drop_column("public_key")
