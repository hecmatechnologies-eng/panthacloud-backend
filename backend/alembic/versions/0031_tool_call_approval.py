"""Record approval provenance on agent_tool_calls

Revision ID: 0031_tool_call_approval
Revises: 0030_knowledge_storage
Create Date: 2026-10-11 00:00:00.000000

ApprovedPlan gated a write tool at runtime but nothing persisted who authorised it, so a write
call in the run log was indistinguishable from one the agent performed on its own authority.
ASI09 asks for an immutable record of what was authorised, not only of what ran.

All three columns are nullable: a read tool is auto-authorised by capability, and writing an
approval for it would imply a review that never happened.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031_tool_call_approval"
down_revision: str | None = "0030_knowledge_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_tool_calls",
        sa.Column("approved_by", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_tool_calls",
        sa.Column("approver_kind", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "agent_tool_calls",
        sa.Column("approved_plan_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_tool_calls", "approved_plan_id")
    op.drop_column("agent_tool_calls", "approver_kind")
    op.drop_column("agent_tool_calls", "approved_by")