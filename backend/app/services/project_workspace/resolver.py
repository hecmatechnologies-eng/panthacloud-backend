"""Resolve a project's workspace from server state, with the tenancy proof applied.

The single place that assembles "everything this project is made of". Every component is looked up
*through the project*, which is itself looked up *through the organization*, so a foreign project is
absent rather than partially resolved. The one binding that is not structurally scoped — a GitHub
installation id is a plain integer on the integration — is checked explicitly.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.assistant import Assistant
from app.models.github_installation import GitHubInstallation
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.models.project import Project
from app.models.website_integration import WebsiteIntegration
from app.services.project_workspace.models import (
    ModelBinding,
    ProjectWorkspace,
    WorkspaceIntegrityError,
)


async def resolve_project_workspace(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> ProjectWorkspace | None:
    """Return the workspace for a project in an organization, or ``None`` if it is not theirs.

    ``None`` is the same answer for "no such project" and "not this organization's project": the
    caller turns it into a 404, so the endpoint cannot be used to enumerate another tenant's ids.
    """
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        return None

    assistant = (
        await db.execute(select(Assistant).where(Assistant.project_id == project.id))
    ).scalar_one_or_none()

    knowledge_base = (
        await db.execute(select(KnowledgeBase).where(KnowledgeBase.project_id == project.id))
    ).scalar_one_or_none()

    document_count = 0
    if knowledge_base is not None:
        document_count = (
            await db.execute(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.knowledge_base_id == knowledge_base.id
                )
            )
        ).scalar_one()

    integration = (
        await db.execute(
            select(WebsiteIntegration).where(WebsiteIntegration.project_id == project.id)
        )
    ).scalar_one_or_none()

    if integration is not None and integration.github_installation_id is not None:
        await _assert_installation_owned_by_organization(
            db,
            organization_id=organization_id,
            integration=integration,
        )

    return ProjectWorkspace(
        organization_id=organization_id,
        project_id=project.id,
        project_name=project.name,
        assistant_id=assistant.id if assistant is not None else None,
        assistant_enabled=bool(assistant is not None and assistant.is_enabled),
        knowledge_base_id=knowledge_base.id if knowledge_base is not None else None,
        knowledge_document_count=int(document_count),
        integration_id=integration.id if integration is not None else None,
        repository=(
            f"{integration.repository_owner}/{integration.repository_name}"
            if integration is not None
            else None
        ),
        default_branch=integration.default_branch if integration is not None else None,
        github_installation_id=(
            integration.github_installation_id if integration is not None else None
        ),
        model=ModelBinding(
            provider=settings.MODEL_PROVIDER,
            model_id=settings.MODEL_ID,
            configured=bool(settings.MODEL_API_KEY),
        ),
    )


async def _assert_installation_owned_by_organization(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    integration: WebsiteIntegration,
) -> None:
    """Fail closed if an integration points at an installation this organization does not own.

    The integration endpoint validates this at creation, but a raw integer column is not a foreign
    key, so the resolver re-checks rather than trusting a write path it does not control. A missing
    row and another tenant's row are the same answer: refuse.
    """
    installation = (
        await db.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.installation_id == integration.github_installation_id,
                GitHubInstallation.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if installation is None:
        raise WorkspaceIntegrityError(
            f"Integration {integration.id} references GitHub installation "
            f"{integration.github_installation_id}, which is not owned by organization "
            f"{organization_id}."
        )
