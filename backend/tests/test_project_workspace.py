"""The workspace resolver: what a project is made of, and that it is one tenant's.

These are the two claims the resolver exists to make, so they are what is tested: the composition
is correct, and a cross-tenant component (or project) is refused rather than mixed in.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import Assistant
from app.models.github_installation import GitHubInstallation
from app.models.knowledge import KnowledgeBase
from app.models.organization import Organization
from app.models.project import Project
from app.models.website_integration import WebsiteIntegration
from app.services.project_workspace import (
    WorkspaceIntegrityError,
    resolve_project_workspace,
)


async def _org_with_project(
    db: AsyncSession, *, org_slug: str, project_slug: str
) -> tuple[Organization, Project]:
    org = Organization(name=org_slug.title(), slug=org_slug)
    db.add(org)
    await db.flush()
    project = Project(organization_id=org.id, name=project_slug.title(), slug=project_slug)
    db.add(project)
    await db.flush()
    return org, project


async def _integration(db: AsyncSession, project: Project, **overrides) -> WebsiteIntegration:
    fields = {
        "project_id": project.id,
        "repository_owner": "acme",
        "repository_name": "marketing",
        "default_branch": "main",
    }
    fields.update(overrides)
    integration = WebsiteIntegration(**fields)
    db.add(integration)
    return integration


@pytest.mark.asyncio
async def test_resolves_every_component_of_a_project(db_session: AsyncSession):
    org, project = await _org_with_project(
        db_session, org_slug="ws-org", project_slug="ws-site"
    )
    assistant = Assistant(project_id=project.id)
    knowledge_base = KnowledgeBase(project_id=project.id, name="Acme KB")
    integration = await _integration(db_session, project)
    db_session.add_all([assistant, knowledge_base])
    await db_session.commit()

    workspace = await resolve_project_workspace(
        db_session, organization_id=org.id, project_id=project.id
    )

    assert workspace is not None
    assert workspace.organization_id == org.id
    assert workspace.project_id == project.id
    assert workspace.project_name == project.name
    assert workspace.assistant_id == assistant.id
    assert workspace.assistant_enabled is True
    assert workspace.knowledge_base_id == knowledge_base.id
    assert workspace.knowledge_document_count == 0
    assert workspace.integration_id == integration.id
    assert workspace.repository == "acme/marketing"
    assert workspace.default_branch == "main"
    assert workspace.components == frozenset({"assistant", "knowledge", "repository"})
    assert workspace.model.provider
    assert workspace.model.model_id


@pytest.mark.asyncio
async def test_a_bare_project_resolves_to_an_empty_workspace(db_session: AsyncSession):
    org, project = await _org_with_project(
        db_session, org_slug="bare-org", project_slug="bare-site"
    )
    await db_session.commit()

    workspace = await resolve_project_workspace(
        db_session, organization_id=org.id, project_id=project.id
    )

    assert workspace is not None
    assert workspace.components == frozenset()
    assert workspace.assistant_id is None
    assert workspace.knowledge_base_id is None
    assert workspace.integration_id is None
    assert workspace.repository is None


@pytest.mark.asyncio
async def test_another_tenants_project_is_absent_not_partial(db_session: AsyncSession):
    _, project_a = await _org_with_project(
        db_session, org_slug="tenant-a", project_slug="site"
    )
    org_b, _ = await _org_with_project(db_session, org_slug="tenant-b", project_slug="site")
    db_session.add_all([Assistant(project_id=project_a.id), KnowledgeBase(project_id=project_a.id, name="KB")])
    await db_session.commit()

    # Org B asks for Org A's project: no composition leaks back, not even the parts.
    assert (
        await resolve_project_workspace(
            db_session, organization_id=org_b.id, project_id=project_a.id
        )
        is None
    )


@pytest.mark.asyncio
async def test_an_installation_owned_by_another_org_fails_closed(db_session: AsyncSession):
    org_a, project_a = await _org_with_project(
        db_session, org_slug="install-a", project_slug="site"
    )
    org_b, _ = await _org_with_project(db_session, org_slug="install-b", project_slug="site")

    # An installation belonging to tenant B, pointed at by tenant A's integration. The write path
    # validates this, but the column is a bare integer, so the resolver must not trust it.
    db_session.add(
        GitHubInstallation(
            organization_id=org_b.id,
            installation_id=987654,
            account_login="install-b",
            account_type="Organization",
            repository_selection="selected",
        )
    )
    await _integration(db_session, project_a, github_installation_id=987654)
    await db_session.commit()

    with pytest.raises(WorkspaceIntegrityError):
        await resolve_project_workspace(
            db_session, organization_id=org_a.id, project_id=project_a.id
        )


@pytest.mark.asyncio
async def test_an_installation_owned_by_the_same_org_resolves(db_session: AsyncSession):
    org, project = await _org_with_project(
        db_session, org_slug="install-ok", project_slug="site"
    )
    db_session.add(
        GitHubInstallation(
            organization_id=org.id,
            installation_id=123456,
            account_login="install-ok",
            account_type="Organization",
            repository_selection="all",
        )
    )
    await _integration(db_session, project, github_installation_id=123456)
    await db_session.commit()

    workspace = await resolve_project_workspace(
        db_session, organization_id=org.id, project_id=project.id
    )

    assert workspace is not None
    assert workspace.github_installation_id == 123456


async def _register(client: AsyncClient, email: str, org_name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "org_name": org_name},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    return token, orgs.json()[0]["id"]


@pytest.mark.asyncio
async def test_workspace_endpoint_reports_a_bare_project(client: AsyncClient):
    token, org_id = await _register(client, "ws_endpoint@example.com", "WS Endpoint")
    hdr = {"Authorization": f"Bearer {token}"}
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects", headers=hdr, json={"name": "Site"}
    )
    project_id = project.json()["id"]

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/workspace", headers=hdr
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["components"] == []
    assert body["integration_id"] is None
    assert body["assistant_id"] is None
    assert body["model"]["provider"]


@pytest.mark.asyncio
async def test_workspace_endpoint_is_tenant_scoped(client: AsyncClient):
    token_a, org_a = await _register(client, "ws_a@example.com", "WS A")
    token_b, _ = await _register(client, "ws_b@example.com", "WS B")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}
    project = await client.post(
        f"/api/v1/organizations/{org_a}/projects", headers=hdr_a, json={"name": "Site"}
    )
    project_id = project.json()["id"]

    # Org B asking for Org A's project is a 404, not a 403: never confirm it exists.
    resp = await client.get(
        f"/api/v1/organizations/{org_a}/projects/{project_id}/workspace", headers=hdr_b
    )

    assert resp.status_code == 404
