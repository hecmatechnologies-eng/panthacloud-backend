"""Rows that already exist when 0019 runs, so its backfill is exercised.

Applied at revision 0018 by `scripts/verify_migration.py --seed`. Two integrations, one of each
enum member, because the backfill only rewrites the non-default member (`GENERIC_HTML`): a single
default row cannot demonstrate that the default was preserved while the other was mapped.
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
    " public_key, framework, created_at, updated_at)"
    " VALUES (:id, :project_id, :owner, 'site', :public_key, :framework, :now, :now)"
)


def _id(connection: sa.Connection) -> str:
    """A UUID in the form this dialect stores: dashless hex on SQLite, canonical on Postgres."""
    value = uuid.uuid4()
    return value.hex if connection.dialect.name == "sqlite" else str(value)


def seed(connection: sa.Connection) -> None:
    now = "2026-09-13 00:00:00"
    organization_id = _id(connection)
    connection.execute(
        ORGANIZATIONS,
        {"id": organization_id, "name": "MigCheck C10", "slug": "migcheck-c10", "now": now},
    )
    for owner, framework in (("acme", "REACT_NEXTJS"), ("globex", "GENERIC_HTML")):
        # website_integrations.project_id is unique, so each integration needs its own project.
        project_id = _id(connection)
        connection.execute(
            PROJECTS,
            {
                "id": project_id,
                "organization_id": organization_id,
                "name": f"MigCheck {owner}",
                "slug": f"migcheck-c10-{owner}",
                "now": now,
            },
        )
        connection.execute(
            INTEGRATIONS,
            {
                "id": _id(connection),
                "project_id": project_id,
                "owner": owner,
                "public_key": f"fussion_pk_migcheck_c10_{owner}",
                "framework": framework,
                "now": now,
            },
        )
