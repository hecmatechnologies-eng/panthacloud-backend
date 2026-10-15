"""Make the channel session identity index actually fire (ADR-004).

Revision ID: 0035_thread_coalesce
Revises: 0034_message_direction

0033 created ``uq_visitor_session_channel_identity`` over
``(project_id, channel, external_id, thread_id)`` and nothing queried it for two releases. The
first code to use it (0035's companion, ``app/channels/sessions.py``) found that the index does
not fire for a top-level conversation.

A conversation with no thread has ``thread_id = NULL``, and NULLs are distinct within a unique
index on both Postgres and SQLite - so a plain column index admits an unbounded number of them.
Verified directly against each engine: rows with ``thread_id`` of NULL, '' and 'x' all coexisted
without a violation. Two deliveries of one guest's first message would each open a session, and the
guest would appear to the assistant as two people. The savepoint recovery in ``sessions.py`` was
written to absorb exactly that conflict and could therefore never fire.

The fix is to make the key total by indexing ``coalesce(thread_id, '')``: no writable value escapes
the constraint. This is a correctness fix, not an optimisation, so the application also writes the
canonical '' - but the index does not rely on that.

Safe to apply over existing data: ``CREATE UNIQUE INDEX`` fails outright if duplicates are present,
so a failure here is the migration correctly reporting that the database already violates the
guarantee it is being given, rather than a migration bug. At time of writing there are zero channel
rows, so there is nothing to collide.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0035_thread_coalesce"
down_revision = "0034_message_direction"
branch_labels = None
depends_on = None

INDEX = "uq_visitor_session_channel_identity"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if INDEX not in {ix["name"] for ix in inspector.get_indexes("visitor_sessions")}:
        # Nothing to repair: an install that has never had the index keeps working, and the model
        # definition is what creates it from here on.
        return

    op.drop_index(INDEX, table_name="visitor_sessions")
    op.create_index(
        INDEX,
        "visitor_sessions",
        ["project_id", "channel", "external_id", sa.text("coalesce(thread_id, '')")],
        unique=True,
        sqlite_where=sa.text("external_id IS NOT NULL"),
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if INDEX not in {ix["name"] for ix in inspector.get_indexes("visitor_sessions")}:
        return

    op.drop_index(INDEX, table_name="visitor_sessions")
    # Restoring the weaker form would reintroduce the defect, so the downgrade says so rather than
    # leaving a landmine for whoever runs it.
    op.create_index(
        INDEX,
        "visitor_sessions",
        ["project_id", "channel", "external_id", "thread_id"],
        unique=True,
        sqlite_where=sa.text("external_id IS NOT NULL"),
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
