"""Organisation-level channel accounts, and a project's choice of one.

Rescopes ``channel_registrations`` from project-owned to organisation-owned. The previous model had
``project_id`` NOT NULL, which meant claiming a number *was* pointing a project at it - so a tenant
with two properties could not connect both numbers and decide later which each project used.

``project_id`` becomes nullable with ``ON DELETE SET NULL``. Deleting a project must not delete the
organisation's credentials, and it must not orphan a number that another project may later select;
deleting the *project* loses a selection, which is what ``project_channels`` records separately.

Existing rows keep their ``project_id``, and this migration seeds a ``project_channels`` row for
each so nothing that worked stops working. A project that had a number before this release keeps
answering on it - silently losing live routing to a schema change would be a far worse outcome than
carrying one redundant column forward for a release.

``project_channels`` carries the two uniqueness constraints described in its model docstring. The
second - one project per account - is forced by inbound routing, not chosen: a webhook names the
business number and nothing else, so two projects on one number would leave the resolver choosing
arbitrarily between two correct answers.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039_organisation_channels"
down_revision = "0038_whatsapp_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Project ownership is no longer implied. SET NULL rather than CASCADE: a deleted project must
    # not take the organisation's connected credentials with it.
    with op.batch_alter_table("channel_registrations") as batch:
        batch.drop_constraint(
            "channel_registrations_project_id_fkey", type_="foreignkey"
        )
        batch.alter_column("project_id", existing_type=sa.UUID(), nullable=True)
        batch.create_foreign_key(
            "channel_registrations_project_id_fkey",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "project_channels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            # create_type=False: `session_channel` was created by 0033 and already exists. Without
            # it this migration tries to CREATE TYPE again and fails with DuplicateObject, which
            # reads like a corrupt database rather than a declaration that is trying to own a type
            # it does not own.
            postgresql.ENUM(
                "web",
                "whatsapp",
                "telegram",
                "email",
                "sms",
                name="session_channel",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "channel_registration_id",
            sa.UUID(),
            sa.ForeignKey("channel_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "channel", name="uq_project_channel_project"),
        sa.UniqueConstraint(
            "channel", "channel_registration_id", name="uq_project_channel_registration"
        ),
    )
    op.create_index("ix_project_channels_project_id", "project_channels", ["project_id"])

    # Carry forward live routing: a registration that had a project keeps answering for it.
    op.execute(
        """
        INSERT INTO project_channels
            (id, project_id, channel, channel_registration_id, selected_at, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            project_id,
            channel,
            id,
            NOW(),
            NOW(),
            NOW()
        FROM channel_registrations
        WHERE project_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_channels_project_id", table_name="project_channels")
    op.drop_table("project_channels")

    with op.batch_alter_table("channel_registrations") as batch:
        batch.drop_constraint(
            "channel_registrations_project_id_fkey", type_="foreignkey"
        )
        # NOT NULL again only works because the project_channels rows are gone; any registration
        # left with a NULL project is a number the organisation connected but never assigned, and
        # restoring NOT NULL would refuse it. That is a genuine data loss and is left visible
        # rather than papered over by deleting rows.
        batch.alter_column("project_id", existing_type=sa.UUID(), nullable=False)
        batch.create_foreign_key(
            "channel_registrations_project_id_fkey",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )