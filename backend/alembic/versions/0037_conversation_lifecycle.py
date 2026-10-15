"""Conversation lifecycle, intent and follow-up schedule.

Revision ID: 0037_conversation_lifecycle
Revises: 0036_channel_registration

Adds the state the staff inbox reads. The prototype's status column was a conversation lifecycle
- whose turn is it - and it had nowhere to live: `MessageStatus` describes one message's delivery,
and a conversation can be waiting on a guest while every one of its messages is `sent`.

Two decisions are load-bearing rather than cosmetic:

- `status` is NOT NULL with no backfill, because every conversation already in the database is one
  this migration is about to make readable. Defaulting existing rows to `answered` would assert
  that the assistant handled them, which for a conversation holding an unapproved draft is the one
  thing that must not be assumed. `awaiting_approval` is the honest starting state: it means "a
  person needs to look at this", which is true of every pre-existing row.

- The follow-up index is partial. Almost every conversation has a NULL `next_follow_up_at`, and an
  index over mostly-NULLs is an index over nothing.

`value` is a plain string rather than an enum on purpose: "high value" is a judgement a hotel makes
about its own guests, and a new one should not need a migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0037_conversation_lifecycle"
down_revision = "0036_channel_registration"
branch_labels = None
depends_on = None


def _type_exists(bind, type_name: str) -> bool:
    """Whether a Postgres type is already present.

    An explicit query rather than ``Enum.create(checkfirst=True)``, which was observed issuing
    CREATE TYPE against a database where the type plainly existed - see 0036.
    """
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": type_name}
        ).first()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # create_type=False, because otherwise adding the column makes SQLAlchemy emit its own CREATE
    # TYPE and collide. See 0036; these are new types, but the same mechanism applies on re-run.
    status = postgresql.ENUM(
        "answered",
        "awaiting_approval",
        "escalated",
        "awaiting_guest",
        "booked",
        "lost",
        name="conversation_status",
        create_type=False,
    )
    intent = postgresql.ENUM(
        "informational",
        "booking",
        "event",
        "complaint",
        "other",
        name="conversation_intent",
        create_type=False,
    )
    if not _type_exists(bind, "conversation_status"):
        status.create(bind)
    if not _type_exists(bind, "conversation_intent"):
        intent.create(bind)

    # Added nullable first, backfilled, then tightened. Adding a NOT NULL column with a default in
    # one step works on Postgres but rewrites the table and, on SQLite, has to be done in a
    # rebuild; the three-step version is the same on both.
    op.add_column("conversations", sa.Column("status", status, nullable=True))
    op.add_column("conversations", sa.Column("intent", intent, nullable=True))
    op.add_column("conversations", sa.Column("value", sa.String(length=16), nullable=True))
    op.add_column("conversations", sa.Column("lost_reason", sa.String(length=255), nullable=True))
    op.add_column(
        "conversations", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Every conversation that exists predates the staff desk. None of them can honestly be called
    # `answered`, and none has been confirmed by a desk, so they all start as needing a human.
    op.execute("UPDATE conversations SET status = 'awaiting_approval' WHERE status IS NULL")

    op.alter_column(
        "conversations",
        "status",
        existing_type=status,
        nullable=False,
        # Kept so a row inserted by older application code mid-deploy does not fail on a column
        # that is NOT NULL. The application never relies on it - it always passes a status.
        server_default="awaiting_approval",
    )
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_index(
        "ix_conversations_follow_up_due",
        "conversations",
        ["next_follow_up_at"],
        sqlite_where=sa.text("next_follow_up_at IS NOT NULL"),
        postgresql_where=sa.text("next_follow_up_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_follow_up_due", table_name="conversations")
    op.drop_index("ix_conversations_status", table_name="conversations")
    for column in (
        "next_follow_up_at",
        "lost_reason",
        "value",
        "intent",
        "status",
    ):
        op.drop_column("conversations", column)
    # The two enum types are left in place. Dropping them here would fail if anything else came to
    # reference them, and leaving them costs nothing - a leftover type is inert.