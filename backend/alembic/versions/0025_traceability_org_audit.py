"""runtime traceability and organization-level audit

Revision ID: 0025_traceability_org_audit
Revises: 0024_org_model_settings
Create Date: 2026-09-16 11:00:00.000000

Two changes that both exist to make the record complete:

1. ``audit_events.project_id`` becomes optional. An organization-level decision — choosing the
   organization's model — has no project to attribute it to, and a NOT NULL column meant such
   changes could not be audited at all.
2. ``messages`` gains ``assistant_version`` and ``prompt_hash``, so an assistant turn can be
   attributed to the definition that produced it. The engineering plane records the same pair on
   ``AgentRun``; this is the runtime's counterpart.

The audit change is wrapped in ``batch_alter_table`` because SQLite cannot ALTER COLUMN: outside
batch mode Alembic's SQLite dialect has nothing to emit, and the schema would keep the old
constraint while Postgres got the new one.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_traceability_org_audit"
down_revision: str | None = "0024_org_model_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.alter_column("project_id", existing_type=sa.Uuid(), nullable=True)

    op.add_column(
        "messages", sa.Column("assistant_version", sa.String(length=50), nullable=True)
    )
    op.add_column("messages", sa.Column("prompt_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "prompt_hash")
    op.drop_column("messages", "assistant_version")

    # An organization-level event has no project to name, so it cannot survive a NOT NULL column.
    # Removed rather than allowed to fail the downgrade on data it could never represent.
    op.execute("DELETE FROM audit_events WHERE project_id IS NULL")

    with op.batch_alter_table("audit_events") as batch:
        batch.alter_column("project_id", existing_type=sa.Uuid(), nullable=False)
