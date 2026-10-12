import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_project, require_permission
from app.api.v1.endpoints._location import CREATED_RESPONSE, created
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.slugs import slugify
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/organizations/{org_id}/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    responses=CREATED_RESPONSE,
    summary="Create a new project inside the organization",
)
async def create_project(
    payload: ProjectCreate,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_CREATE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> ProjectRead:
    org, _ = tenant
    slug = payload.slug or f"{slugify(payload.name, 'project')}-{uuid.uuid4().hex[:6]}"

    project = Project(
        organization_id=org.id,
        name=payload.name,
        slug=slug,
        description=payload.description,
    )
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        # UNIQUE(organization_id, slug) is the authority. A pre-check would race with a
        # concurrent create and surface as a 500; one insert gives one honest answer.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project slug '{slug}' is already taken in this organization.",
        ) from None
    await db.refresh(project)

    created(response, "organizations", str(org.id), "projects", str(project.id))
    return ProjectRead.model_validate(project)


@router.get(
    "",
    response_model=list[ProjectRead],
    summary="List all projects in the organization",
)
async def list_projects(
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProjectRead]:
    org, _ = tenant
    stmt = (
        select(Project)
        .where(Project.organization_id == org.id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    result = await db.execute(stmt)
    projects = result.scalars().all()
    return [ProjectRead.model_validate(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Retrieve project details within tenant scope",
)
async def get_project(
    project: Annotated[Project, Depends(get_current_project)],
) -> ProjectRead:
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update project details within tenant scope",
)
async def update_project(
    payload: ProjectUpdate,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_MODIFY)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectRead:
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description

    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project and all associated integrations within tenant scope",
)
async def delete_project(
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_DELETE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await db.delete(project)
    await db.commit()

