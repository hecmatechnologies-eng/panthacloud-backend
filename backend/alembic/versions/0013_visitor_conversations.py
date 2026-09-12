"""visitor sessions, conversations and messages

Revision ID: 0013_visitor_conversations
Revises: 0012_public_key_allowed_origins
Create Date: 2026-09-12 22:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_visitor_conversations"
down_revision: str | None = "0012_public_key_allowed_origins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Inlined, not imported from app.core.origins: a migration must keep producing the same schema
# whatever the application later does with the constant.
MAX_ORIGIN_LENGTH = 255

message_role = sa.Enum("VISITOR", "ASSISTANT", name="message_role")


def upgrade() -> None:
    op.create_table(
        "visitor_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=MAX_ORIGIN_LENGTH), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["website_integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_visitor_sessions_integration_id"),
        "visitor_sessions",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_visitor_sessions_expires_at"),
        "visitor_sessions",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["visitor_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversations_session_id"), "conversations", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_conversations_retention_expires_at"),
        "conversations",
        ["retention_expires_at"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_message_conversation_created",
        "messages",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_message_conversation_created", table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_conversations_retention_expires_at"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_session_id"), table_name="conversations")
    op.drop_table("conversations")

    op.drop_index(op.f("ix_visitor_sessions_expires_at"), table_name="visitor_sessions")
    op.drop_index(op.f("ix_visitor_sessions_integration_id"), table_name="visitor_sessions")
    op.drop_table("visitor_sessions")

    # Native ENUM is a separate Postgres type; dropping the table does not drop it.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        message_role.drop(bind, checkfirst=True)
