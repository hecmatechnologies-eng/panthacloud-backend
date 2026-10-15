"""A messaging address a project has claimed (ADR-004).

Revision ID: 0036_channel_registration
Revises: 0035_thread_coalesce

The channel counterpart to ``allowed_origals``. A webhook carries a ``wa_id`` and nothing else
identifying, so this table is what turns that into a tenant.

Uniqueness spans ``(channel, external_identifier)`` globally, not per organisation: two tenants
claiming one number is a conflict to report, and a per-organisation constraint would make the second
claim silently win depending on insert order. It also spans ``is_active`` - a retired registration
keeps holding its address, so reactivation cannot collide with a number handed on since.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0036_channel_registration"
down_revision = "0035_thread_coalesce"
branch_labels = None
depends_on = None


def _type_exists(bind, type_name: str) -> bool:
    """Whether a Postgres type is already present.

    ``Enum.create(checkfirst=True)`` is supposed to answer this and did not: against a database
    where ``session_channel`` plainly existed it still issued ``CREATE TYPE`` and the migration died
    on DuplicateObject. Same reason 0034 queries ``pg_enum`` directly - a migration that only works
    from a clean state cannot be deployed onto an existing one, which is the only place migrations
    ever run.
    """
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": type_name}
        ).first()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Reuses the enum 0033 created for visitor_sessions.channel rather than adding a second
    # vocabulary for the same set. Values are spelled out rather than imported, so this migration
    # keeps working after the application renames one - and a rename is a migration of its own.
    #
    # create_type=False, because otherwise `create_table` emits its own CREATE TYPE for the column
    # and collides with the type that already exists. The only exception to that is 0033, where the
    # same object is passed to `.create()` first, which marks it as handled.
    channel = postgresql.ENUM(
        "web",
        "whatsapp",
        "telegram",
        "email",
        "sms",
        name="session_channel",
        create_type=False,
    )
    if not _type_exists(bind, "session_channel"):
        channel.create(bind)

    op.create_table(
        "channel_registrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        # The same enum object as the explicit create above, not a second spelling of it. An enum
        # built with only a name - or with `values_callable`, which is application-side and is not
        # what the DDL layer reads - makes SQLAlchemy emit its own `CREATE TYPE ... AS ENUM ()`
        # while creating the table, which collides with the type that already exists. Observed.
        sa.Column("channel", channel, nullable=False),
        sa.Column("external_identifier", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_channel_registrations_organization_id",
        "channel_registrations",
        ["organization_id"],
    )
    op.create_index(
        "ix_channel_registrations_project_id", "channel_registrations", ["project_id"]
    )
    op.create_index(
        "ix_channel_registration_project_channel",
        "channel_registrations",
        ["project_id", "channel"],
    )
    op.create_index(
        "uq_channel_registration_address",
        "channel_registrations",
        ["channel", "external_identifier"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_channel_registration_address", table_name="channel_registrations")
    op.drop_index(
        "ix_channel_registration_project_channel", table_name="channel_registrations"
    )
    op.drop_index("ix_channel_registrations_project_id", table_name="channel_registrations")
    op.drop_index(
        "ix_channel_registrations_organization_id", table_name="channel_registrations"
    )
    op.drop_table("channel_registrations")
    # The enum is deliberately left in place: visitor_sessions.channel uses it too, and dropping it
    # here would break that table on the way down.