"""composite indexes for model usage and audit queries

Revision ID: 0026_composite_indexes
Revises: 0025_traceability_org_audit
Create Date: 2026-09-17 12:00:00.000000
	1. model_usage: (project_id, created_at) and (project_id, integration_id)
	2. audit_events: (organization_id, created_at) and (project_id, created_at)
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_composite_indexes"
down_revision: str | None = "0025_traceability_org_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_model_usage_project_created",
        "model_usage",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_usage_project_int",
        "model_usage",
        ["project_id", "integration_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_org_created",
        "audit_events",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_project_created",
        "audit_events",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_project_created", table_name="audit_events")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_index("ix_model_usage_project_int", table_name="model_usage")
    op.drop_index("ix_model_usage_project_created", table_name="model_usage")
