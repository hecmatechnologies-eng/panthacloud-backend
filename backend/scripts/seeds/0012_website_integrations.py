"""Rows that already exist when 0012 runs, so its public_key backfill is exercised.

Applied at revision 0011 by `scripts/verify_migration.py --seed`. Two integrations, because the
backfill must give each row its *own* key, which a single row cannot demonstrate.
"""

import uuid

import sqlalchemy as sa

ORGANIZATIONS = sa.text(
    "INSERT INTO organizations (id, name, slug, created_at, updated_at)"
    " VALUES (:id, :name, :slug, :now, :now)"
)
PROJECTS = sa.text(
    "INSERT INTO projects (id, organization_id, name, slug, created_at, updated_at)"
    " VALUES (:id, :organization_id, :name, :slug, :now, :now)"
)
INTEGRATIONS = sa.text(
    "INSERT INTO website_integrations (id, project_id, repository_owner, repository_name,"
    " created_at, updated_at) VALUES (:id, :project_id, :owner, 'site', :now, :now)"
)


def _id(connection: sa.Connection) -> str:
    """A UUID in the form this dialect stores: dashless hex on SQLite, canonical on Postgres."""
    value = uuid.uuid4()
    return value.hex if connection.dialect.name == "sqlite" else str(value)


def seed(connection: sa.Connection) -> None:
    now = "2026-09-11 00:00:00"
    organization_id = _id(connection)
    connection.execute(
        ORGANIZATIONS,
        {"id": organization_id, "name": "MigCheck", "slug": "migcheck", "now": now},
    )
    for owner in ("acme", "globex"):
        # website_integrations.project_id is unique, so each integration needs its own project.
        project_id = _id(connection)
        connection.execute(
            PROJECTS,
            {
                "id": project_id,
                "organization_id": organization_id,
                "name": f"MigCheck {owner}",
                "slug": f"migcheck-{owner}",
                "now": now,
            },
        )
        connection.execute(
            INTEGRATIONS,
            {"id": _id(connection), "project_id": project_id, "owner": owner, "now": now},
        )
