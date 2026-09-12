"""Rows that already exist when 0015 runs, so its NOT NULL backfills are exercised.

Applied at revision 0014 by `scripts/verify_migration.py --seed`. One organization → project with a
knowledge base, and one integration → session → conversation → message, so both altered tables
(`knowledge_bases`, `messages`) hold pre-existing rows when the server-defaulted columns are added.
An empty table cannot demonstrate that the defaults backfill.
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
KNOWLEDGE_BASES = sa.text(
    "INSERT INTO knowledge_bases (id, project_id, name, description, created_at, updated_at)"
    " VALUES (:id, :project_id, :name, NULL, :now, :now)"
)
INTEGRATIONS = sa.text(
    "INSERT INTO website_integrations (id, project_id, repository_owner, repository_name,"
    " public_key, created_at, updated_at)"
    " VALUES (:id, :project_id, 'acme', 'site', :public_key, :now, :now)"
)
SESSIONS = sa.text(
    "INSERT INTO visitor_sessions (id, integration_id, origin, expires_at, created_at, updated_at)"
    " VALUES (:id, :integration_id, 'https://shop.example.com', :now, :now, :now)"
)
CONVERSATIONS = sa.text(
    "INSERT INTO conversations (id, session_id, retention_expires_at, created_at, updated_at)"
    " VALUES (:id, :session_id, :now, :now, :now)"
)
MESSAGES = sa.text(
    "INSERT INTO messages (id, conversation_id, role, content, created_at, updated_at)"
    " VALUES (:id, :conversation_id, 'VISITOR', 'hello', :now, :now)"
)


def _id(connection: sa.Connection) -> str:
    """A UUID in the form this dialect stores: dashless hex on SQLite, canonical on Postgres."""
    value = uuid.uuid4()
    return value.hex if connection.dialect.name == "sqlite" else str(value)


def seed(connection: sa.Connection) -> None:
    now = "2026-09-12 00:00:00"
    organization_id = _id(connection)
    connection.execute(
        ORGANIZATIONS,
        {"id": organization_id, "name": "MigCheck B6", "slug": "migcheck-b6", "now": now},
    )
    project_id = _id(connection)
    connection.execute(
        PROJECTS,
        {
            "id": project_id,
            "organization_id": organization_id,
            "name": "MigCheck B6",
            "slug": "migcheck-b6",
            "now": now,
        },
    )
    connection.execute(
        KNOWLEDGE_BASES,
        {"id": _id(connection), "project_id": project_id, "name": "MigCheck KB", "now": now},
    )
    integration_id = _id(connection)
    connection.execute(
        INTEGRATIONS,
        {
            "id": integration_id,
            "project_id": project_id,
            "public_key": "fussion_pk_migcheck_b6",
            "now": now,
        },
    )
    session_id = _id(connection)
    connection.execute(SESSIONS, {"id": session_id, "integration_id": integration_id, "now": now})
    conversation_id = _id(connection)
    connection.execute(CONVERSATIONS, {"id": conversation_id, "session_id": session_id, "now": now})
    connection.execute(MESSAGES, {"id": _id(connection), "conversation_id": conversation_id, "now": now})
