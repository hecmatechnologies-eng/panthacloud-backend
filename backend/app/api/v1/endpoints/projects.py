import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_project, require_permission
from app.api.v1.endpoints._location import CREATED_RESPONSE, created
from app.api.v1.endpoints._pagination import (
    InvalidCursor,
    cursor_http_error,
    decode_cursor,
    encode_cursor,
    next_link,
    parse_timestamp,
)
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
    request: Request,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    # Declared before the defaulted query params below: `response` has no default of its own,
    # and Python will not accept a non-defaulted parameter after one that has a default.
    response: Response,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> list[ProjectRead]:
    org, _ = tenant
    stmt = select(Project).where(Project.organization_id == org.id)

    if cursor:
        # Keyset on the same (created_at, id) DESC ordering used below, so a project created
        # mid-pagination does not shift the window and cause a row to be served twice or missed.
        try:
            state = decode_cursor(cursor)
            stmt = stmt.where(
                tuple_(Project.created_at, Project.id)
                < tuple_(parse_timestamp(state["created_at"]), uuid.UUID(state["id"]))
            )
        except (InvalidCursor, KeyError, ValueError):
            raise cursor_http_error() from None

    order = (Project.created_at.desc(), Project.id.desc())
    if limit is None:
        result = await db.execute(stmt.order_by(*order))
        return [ProjectRead.model_validate(p) for p in result.scalars().all()]

    # limit + 1: the extra row is how we know another page exists without a COUNT.
    result = await db.execute(stmt.order_by(*order).limit(limit + 1))
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]

    if has_more:
        last = rows[-1]
        response.headers["Link"] = next_link(
            request_path=request.url.path,
            params={},
            limit=limit,
            cursor=encode_cursor({"created_at": last.created_at, "id": str(last.id)}),
        )

    return [ProjectRead.model_validate(p) for p in rows]


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

