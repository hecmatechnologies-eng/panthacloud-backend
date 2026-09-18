"""replace the website_framework enum with a skill id string

Revision ID: 0019_framework_skill_id
Revises: 0018_website_analyses
Create Date: 2026-09-13 03:30:00.000000

FR-082: the stored framework identifier becomes a skill id string, so adding a framework is a new
skill package rather than an enum value and a migration.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_framework_skill_id"
down_revision: str | None = "0018_website_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Inlined: a migration must keep producing the same result whatever the application later does.
_DEFAULT_SKILL_ID = "nextjs-app-router"
_GENERIC_HTML_SKILL_ID = "generic-html"


def upgrade() -> None:
    op.add_column(
        "website_integrations",
        sa.Column(
            "framework_skill_id",
            sa.String(length=100),
            server_default=_DEFAULT_SKILL_ID,
            nullable=False,
        ),
    )
    bind = op.get_bind()
    # The enum stored member names; map the one non-default member.
    bind.execute(
        sa.text(
            "UPDATE website_integrations SET framework_skill_id = :generic"
            " WHERE framework = 'GENERIC_HTML'"
        ),
        {"generic": _GENERIC_HTML_SKILL_ID},
    )
    with op.batch_alter_table("website_integrations") as batch_op:
        batch_op.drop_column("framework")
    if bind.dialect.name == "postgresql":
        sa.Enum(name="website_framework").drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    website_framework = sa.Enum("REACT_NEXTJS", "GENERIC_HTML", name="website_framework")
    # Postgres does not create a type implicitly on ADD COLUMN; the upgrade dropped it.
    website_framework.create(bind, checkfirst=True)
    op.add_column(
        "website_integrations",
        sa.Column("framework", website_framework, server_default="REACT_NEXTJS", nullable=False),
    )
    bind.execute(
        sa.text(
            "UPDATE website_integrations SET framework = 'GENERIC_HTML'"
            " WHERE framework_skill_id = :generic"
        ),
        {"generic": _GENERIC_HTML_SKILL_ID},
    )
    with op.batch_alter_table("website_integrations") as batch_op:
        batch_op.drop_column("framework_skill_id")
