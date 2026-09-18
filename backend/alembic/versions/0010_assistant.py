"""assistant configuration

Revision ID: 0010_assistant
Revises: 0009_knowledge_base
Create Date: 2026-09-08 20:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_assistant"
down_revision: str | None = "0009_knowledge_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

assistant_position = sa.Enum(
    "BOTTOM_RIGHT", "BOTTOM_LEFT",
    name="assistant_position",
)


def upgrade() -> None:
    op.create_table(
        "assistants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), server_default="Fussion Assistant", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("welcome_message", sa.Text(), server_default="Hi! How can I help you today?", nullable=False),
        sa.Column("system_instructions", sa.Text(), nullable=True),
        sa.Column("brand_color", sa.String(length=20), server_default="#6366F1", nullable=False),
        sa.Column("text_color", sa.String(length=20), server_default="#FFFFFF", nullable=False),
        sa.Column("position", assistant_position, server_default="BOTTOM_RIGHT", nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("starter_prompt", sa.Text(), server_default="What can you tell me about your products?", nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_assistant_project_id"),
    )
    op.create_index(op.f("ix_assistants_project_id"), "assistants", ["project_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_assistants_project_id"), table_name="assistants")
    op.drop_table("assistants")
    # For postgresql, drop enum type if applicable
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        assistant_position.drop(bind, checkfirst=True)
