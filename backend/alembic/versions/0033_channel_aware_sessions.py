"""Channel-aware visitor sessions: a conversation without a website widget.

Revision ID: 0033_channel_aware_sessions
Revises: 0032_knowledge_uploaded_by
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0033_channel_aware_sessions"
down_revision = "0032_knowledge_uploaded_by"
branch_labels = None
depends_on = None

channel = sa.Enum("web", "whatsapp", "telegram", "email", "sms", name="session_channel")


def upgrade() -> None:
    # 1. Add the channel enum. Created here rather than relying on create_all, because a
    #    non-existent enum type is not added implicitly when a column starts using it.
    channel.create(op.get_bind(), checkfirst=True)

    # 2. New columns, all nullable for now so existing rows survive and can be backfilled.
    op.add_column(
        "visitor_sessions",
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "visitor_sessions",
        sa.Column("channel", channel, nullable=True, server_default="web"),
    )
    op.add_column("visitor_sessions", sa.Column("external_id", sa.String(255), nullable=True))
    op.add_column("visitor_sessions", sa.Column("thread_id", sa.String(255), nullable=True))

    # 3. Backfill the project from the integration every existing session already had.
    #    project_id cannot be set NOT NULL until this has run, and cannot be added NOT NULL with a
    #    default because the value is only derivable through the join.
    op.execute(
        """
        UPDATE visitor_sessions
        SET project_id = website_integrations.project_id
        FROM website_integrations
        WHERE visitor_sessions.integration_id = website_integrations.id
        """
    )

    # 4. Now that every row has one, make it required.
    op.alter_column("visitor_sessions", "project_id", nullable=False)
    op.create_index(
        "ix_visitor_sessions_project_id", "visitor_sessions", ["project_id"], unique=False
    )

    # 5. The integration is provenance now, not the tenancy anchor. A WhatsApp conversation has no
    #    widget behind it, and a NOT NULL column here forbade every channel we are building.
    #    'origin' relaxes with it: a phone number has no Origin header.
    op.alter_column("visitor_sessions", "integration_id", nullable=True)
    op.alter_column("visitor_sessions", "origin", nullable=True)

    # 6. channel defaults to 'web' for every existing row, but is NOT NULL going forward so a
    #    session's channel is always stated rather than inferred.
    op.alter_column("visitor_sessions", "channel", nullable=False)

    # 7. One conversation per person per channel per project. Partial, so widget rows - which have
    #    no external id - do not participate. See the model's docstring for why this is a partial
    #    index rather than a plain one relying on NULL-distinctness.
    op.create_index(
        "uq_visitor_session_channel_identity",
        "visitor_sessions",
        ["project_id", "channel", "external_id", "thread_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
        sqlite_where=sa.text("external_id IS NOT NULL"),
    )

    # The FK is added last so the backfill never has to respect it mid-flight. SQLite needs the
    # table rebuilt for a foreign key, and Alembic's batch mode does that copy.
    with op.batch_alter_table("visitor_sessions") as batch:
        batch.create_foreign_key(
            "fk_visitor_sessions_project_id",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    # Channel sessions cannot survive: they have no integration, which was NOT NULL. Refusing here
    # is the honest outcome - a silent loss of live guest conversations is worse than a failed
    # rollback the operator can see and plan around.
    orphan = op.get_bind().execute(
        sa.text("SELECT count(*) FROM visitor_sessions WHERE integration_id IS NULL")
    ).scalar_one()
    if orphan:
        raise RuntimeError(
            f"cannot downgrade: {orphan} session(s) belong to a channel with no website "
            f"integration. Delete or migrate them before rolling back to 0032."
        )

    with op.batch_alter_table("visitor_sessions") as batch:
        batch.drop_constraint("fk_visitor_sessions_project_id", type_="foreignkey")

    op.drop_index("uq_visitor_session_channel_identity", table_name="visitor_sessions")
    op.drop_index("ix_visitor_sessions_project_id", table_name="visitor_sessions")
    op.drop_column("visitor_sessions", "thread_id")
    op.drop_column("visitor_sessions", "external_id")
    op.drop_column("visitor_sessions", "channel")
    op.drop_column("visitor_sessions", "project_id")
    channel.drop(op.get_bind(), checkfirst=True)

    op.alter_column("visitor_sessions", "integration_id", nullable=False)
    op.alter_column("visitor_sessions", "origin", nullable=False)