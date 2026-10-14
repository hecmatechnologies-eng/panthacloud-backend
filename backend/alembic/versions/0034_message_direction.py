"""A unified inbound/outbound message record (ADR-004, K5).

Revision ID: 0034_message_direction
Revises: 0033_channel_aware_sessions
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0034_message_direction"
down_revision = "0033_channel_aware_sessions"
branch_labels = None
depends_on = None

# 'assistant' is added to the existing message_role type.
role = sa.Enum("VISITOR", "ASSISTANT", "HUMAN_OPERATOR", name="message_role")
# The type as it exists before this migration. Swapped rather than ALTERed: ALTER TYPE ... ADD VALUE
# cannot run inside Alembic's transaction on older Postgres, and working around that with an explicit
# COMMIT ends the transaction Alembic is managing - which makes `alembic upgrade head` exit 0 while
# leaving the version table unmoved, so the migration silently re-runs on every subsequent command.
# Observed, not theorised. A fresh type plus a swap is one transaction and portable.
role_before = sa.Enum("VISITOR", "ASSISTANT", name="message_role")
direction = sa.Enum("inbound", "outbound", name="message_direction")
status = sa.Enum("drafted", "awaiting_approval", "sent", "failed", name="message_status")


def _has_label(bind, type_name: str, label: str) -> bool:
    """Whether a Postgres enum type already carries a label.

    Written as a direct query because SQLAlchemy's ``Enum`` has no ``exists()``, and because this
    migration has to cope with the state an *interrupted* earlier attempt leaves behind: a type
    widened by ``ALTER TYPE`` that committed while the rest of the migration rolled back. A
    migration that only works from a clean state is a migration that cannot be deployed after a
    failure.
    """
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :type AND e.enumlabel = :label"
            ),
            {"type": type_name, "label": label},
        ).first()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # A column cannot start using a type that does not exist.
    role.create(bind, checkfirst=True)
    direction.create(bind, checkfirst=True)
    status.create(bind, checkfirst=True)

    if not _has_label(bind, "message_role", "HUMAN_OPERATOR"):
        op.execute(
            "ALTER TABLE messages ALTER COLUMN role TYPE message_role "
            "USING role::text::message_role"
        )
        role_before.drop(bind, checkfirst=True)

    op.add_column("messages", sa.Column("direction", direction, nullable=True))
    op.add_column("messages", sa.Column("status", status, nullable=True))
    op.add_column("messages", sa.Column("external_message_id", sa.String(255), nullable=True))

    # Backfill direction from role, which is the only signal the existing rows carry: a guest wrote
    # theirs, the assistant wrote ours. Done before the NOT NULL, which cannot be satisfied by a
    # default because the correct value differs per row.
    op.execute("UPDATE messages SET direction = 'inbound' WHERE role = 'VISITOR'")
    op.execute(
        "UPDATE messages SET direction = 'outbound' WHERE role IN ('ASSISTANT', 'HUMAN_OPERATOR')"
    )
    # Everything already in the table was sent - the assistant replied in the same request that
    # inserted it. Left NULL on inbound rows, where a delivery state would be a fiction.
    op.execute("UPDATE messages SET status = 'sent' WHERE role <> 'VISITOR'")

    op.alter_column("messages", "direction", nullable=False)

    # Idempotency enforced by the database. Two concurrent retries of one webhook are the normal
    # case when a provider retries a slow response, and an application-level "seen this id?"
    # check loses that race; the constraint does not.
    #
    # The WHERE clause is defensive rather than load-bearing: NULLs are distinct in a unique index
    # by default in both engines, so a plain index would also admit rows with no provider id. It
    # keeps that behaviour independent of a default Postgres 15+ can override per-type.
    op.create_index(
        "uq_message_external_id",
        "messages",
        ["conversation_id", "external_message_id"],
        unique=True,
        postgresql_where=sa.text("external_message_id IS NOT NULL"),
        sqlite_where=sa.text("external_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_message_external_id", table_name="messages")
    op.drop_column("messages", "external_message_id")
    op.drop_column("messages", "status")
    op.drop_column("messages", "direction")

    bind = op.get_bind()
    status.drop(bind, checkfirst=True)
    direction.drop(bind, checkfirst=True)

    # message_role is left as-is. Narrowing it needs the same type swap in reverse, under live rows
    # that may already contain HUMAN_OPERATOR; rewriting the type to discard them silently is a
    # worse outcome than a type carrying one label nobody writes yet.