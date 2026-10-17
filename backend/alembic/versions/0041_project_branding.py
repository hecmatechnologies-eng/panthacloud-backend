"""project_branding: a project's outward identity.

One row per project, and none at all is a valid state. A tenant who has not told us who they are
still gets replies - unstyled, with no footer. Failing to send because branding is missing would be
the wrong trade, and the alternative (a platform default) would put one tenant's identity in the
code where the next tenant would inherit it.

``social_links`` is JSON rather than a child table: four entries, only ever read together, rendered
into one footer. A table would add a join and an ordering column to store a dict.

``accent_colour`` is nullable and unvalidated at the database level. The value is normalised at
render time (`app.channels.email.templates.normalise_colour`), so a typo costs a tenant their accent
rather than their ability to send mail.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0041_project_branding"
down_revision = "0040_unsubscribe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_branding",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("business_name", sa.String(length=160), nullable=False),
        sa.Column("tagline", sa.String(length=160), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("accent_colour", sa.String(length=7), nullable=True),
        sa.Column("postal_address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("contact_email", sa.String(length=500), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("social_links", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("footer_note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique on project_id, so "get or create the branding for this project" is unambiguous and a
    # second concurrent insert is refused rather than silently producing two brands.
    op.create_index(
        "ix_project_branding_project_id",
        "project_branding",
        ["project_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_project_branding_project_id", table_name="project_branding")
    op.drop_table("project_branding")