"""organization model settings

Revision ID: 0024_org_model_settings
Revises: 0023_user_accounts_oauth
Create Date: 2026-09-16 10:00:00.000000

Step: give an organization the model its assistants run on (FR-072, FR-075).

One row per organization, and only for organizations that have chosen: the absence of a row is the
deployment default, so nothing has to be backfilled and a new organization is configured by doing
nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_org_model_settings"
down_revision: str | None = "0023_user_accounts_oauth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_model_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_model_settings_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", name="uq_organization_model_settings_organization_id"
        ),
    )
    op.create_index(
        "ix_organization_model_settings_organization_id",
        "organization_model_settings",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_model_settings_organization_id",
        table_name="organization_model_settings",
    )
    op.drop_table("organization_model_settings")
