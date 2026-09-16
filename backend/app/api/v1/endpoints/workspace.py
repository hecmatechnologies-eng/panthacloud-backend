"""Project workspace read (Option A).

Read-only: the resolver has no side effects, so this endpoint is safe to call while rendering.
Tenancy is resolved by ``get_current_project`` before the resolver runs; the resolver re-checks the
project against the organization, which is deliberate — the same resolver is called by agents that
have no HTTP dependency to lean on.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_project, require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.schemas.workspace import ProjectWorkspaceRead
from app.services.project_workspace import resolve_project_workspace

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/workspace",
    tags=["Workspace"],
)


@router.get(
    "",
    response_model=ProjectWorkspaceRead,
    summary="Resolve a project's components and runtime bindings",
)
async def get_project_workspace(
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectWorkspaceRead:
    org, _ = tenant
    workspace = await resolve_project_workspace(
        db, organization_id=org.id, project_id=project.id
    )
    if workspace is None:
        # `get_current_project` already scopes to the organization, so this is unreachable unless
        # the project was deleted mid-request. Kept because the resolver is the source of truth.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in organization.",
        )
    return ProjectWorkspaceRead.from_workspace(workspace)
