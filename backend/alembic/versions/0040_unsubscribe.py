"""one-click unsubscribe state on a visitor session.

Adds ``unsubscribed_at`` and ``unsubscribe_token`` to ``visitor_sessions``.

**Why email needs this and the other channels do not.** A reply goes to an address that never
asked to hear from us. Gmail treats automated mail as bulk by default and, since February 2024,
requires a one-click opt-out from anyone sending that volume. Without it we are a sender asking
people to trust us while offering them no way to decline - which is both the wrong behaviour and
the one most likely to be filtered.

``unsubscribed_at``
    When the guest opted out, or NULL. Retention only: nothing is deleted, because the transcript is
    still the hotel's record of what was asked. Suppressing *sends* does not require erasing the
    history that produced them.

``unsubscribe_token``
    An opaque random value the guest's mail client will POST to. Random rather than derived from
    the row id or the address, because the one-click endpoint is unauthenticated by specification -
    RFC 8058 requires the request to succeed without credentials, since the mail client sending it
    has no session with us. A guessable token would let anyone unsubscribe anyone.

Both nullable. ``unsubscribe_token`` is populated lazily, only when an email reply actually needs a
link, so WhatsApp and widget sessions never carry a value that means nothing on those channels.

This suppresses *automated* sends only. It deliberately does not auto-resubscribe someone who writes
in again: they may have unsubscribed from a list while still expecting an answer to the message
they actually sent, and quietly reversing a person's stated wish on the strength of one email is
worse than making staff aware. Inbound is still recorded and still visible to staff.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040_unsubscribe"
down_revision = "0039_organisation_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visitor_sessions",
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "visitor_sessions",
        sa.Column("unsubscribe_token", sa.String(64), nullable=True),
    )
    # Partial unique on IS NOT NULL, for the same reason `phone_number_id` is partial: the token is
    # only meaningful when present, and a plain unique index would forbid every NULL after the
    # first row. Token equality is the only lookup the one-click endpoint performs, so this index
    # both enforces uniqueness and serves the query.
    op.create_index(
        "uq_visitor_session_unsubscribe_token",
        "visitor_sessions",
        ["unsubscribe_token"],
        unique=True,
        postgresql_where=sa.text("unsubscribe_token IS NOT NULL"),
        sqlite_where=sa.text("unsubscribe_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_visitor_session_unsubscribe_token", table_name="visitor_sessions")
    op.drop_column("visitor_sessions", "unsubscribe_token")
    op.drop_column("visitor_sessions", "unsubscribed_at")