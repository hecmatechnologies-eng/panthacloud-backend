from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_project, get_current_repository, require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.integration import Integration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository, RepositoryStatus
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryRead,
    RepositoryUpdate,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories",
    tags=["Repositories"],
)

VALID_STATUS_TRANSITIONS: dict[RepositoryStatus, set[RepositoryStatus]] = {
    RepositoryStatus.PENDING: {
        RepositoryStatus.PENDING,
        RepositoryStatus.CONNECTED,
        RepositoryStatus.DISCONNECTED,
        RepositoryStatus.ERROR,
    },
    RepositoryStatus.CONNECTED: {
        RepositoryStatus.CONNECTED,
        RepositoryStatus.DISCONNECTED,
        RepositoryStatus.ERROR,
    },
    RepositoryStatus.DISCONNECTED: {
        RepositoryStatus.DISCONNECTED,
        RepositoryStatus.CONNECTED,
        RepositoryStatus.ERROR,
    },
    RepositoryStatus.ERROR: {
        RepositoryStatus.ERROR,
        RepositoryStatus.PENDING,
        RepositoryStatus.CONNECTED,
        RepositoryStatus.DISCONNECTED,
    },
}


def to_repository_read(repo: Repository) -> RepositoryRead:
    return RepositoryRead(
        id=repo.id,
        project_id=repo.project_id,
        integration_id=repo.integration_id,
        provider=repo.provider,
        name=repo.name,
        full_name=repo.full_name,
        external_id=repo.external_id,
        default_branch=repo.default_branch,
        url=repo.url,
        status=repo.status,
        metadata=repo.metadata_,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


@router.post(
    "",
    response_model=RepositoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new external repository for the project",
)
async def create_repository(
    payload: RepositoryCreate,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_CREATE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RepositoryRead:
    # 1. Resolve integration and verify it belongs to the active project
    stmt = select(Integration).where(Integration.id == payload.integration_id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()

    if not integration or integration.project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration does not belong to this project.",
        )

    # 2. Enforce provider compatibility
    if payload.provider.value != integration.provider.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Repository provider '{payload.provider.value}' is incompatible "
                f"with integration provider '{integration.provider.value}'."
            ),
        )

    # 3. Enforce external identity uniqueness per integration
    stmt = select(Repository).where(
        Repository.integration_id == payload.integration_id,
        Repository.external_id == payload.external_id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository with external ID '{payload.external_id}' is already registered for this integration.",
        )

    repo = Repository(
        project_id=project.id,
        integration_id=payload.integration_id,
        provider=payload.provider,
        name=payload.name,
        full_name=payload.full_name,
        external_id=payload.external_id,
        default_branch=payload.default_branch,
        url=payload.url,
        status=payload.status,
        metadata_=payload.metadata,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    return to_repository_read(repo)


@router.get(
    "",
    response_model=list[RepositoryRead],
    summary="List all registered repositories for the project",
)
async def list_repositories(
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RepositoryRead]:
    stmt = (
        select(Repository)
        .where(Repository.project_id == project.id)
        .order_by(Repository.created_at.desc())
    )
    result = await db.execute(stmt)
    repositories = result.scalars().all()
    return [to_repository_read(repo) for repo in repositories]


@router.get(
    "/{repository_id}",
    response_model=RepositoryRead,
    summary="Retrieve repository details within project scope",
)
async def get_repository(
    repository: Annotated[Repository, Depends(get_current_repository)],
) -> RepositoryRead:
    return to_repository_read(repository)


@router.patch(
    "/{repository_id}",
    response_model=RepositoryRead,
    summary="Update repository metadata or connection status",
)
async def update_repository(
    payload: RepositoryUpdate,
    repository: Annotated[Repository, Depends(get_current_repository)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_MODIFY)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RepositoryRead:
    if payload.name is not None:
        repository.name = payload.name

    if payload.full_name is not None:
        repository.full_name = payload.full_name

    if payload.default_branch is not None:
        repository.default_branch = payload.default_branch

    if payload.url is not None:
        repository.url = payload.url

    if payload.metadata is not None:
        updated_meta = dict(repository.metadata_)
        updated_meta.update(payload.metadata)
        repository.metadata_ = updated_meta

    if payload.status is not None:
        allowed = VALID_STATUS_TRANSITIONS.get(repository.status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state transition from '{repository.status.value}' to '{payload.status.value}'.",
            )
        repository.status = payload.status

    await db.commit()
    await db.refresh(repository)
    return to_repository_read(repository)


@router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a registered repository from the project",
)
async def delete_repository(
    repository: Annotated[Repository, Depends(get_current_repository)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_DELETE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await db.delete(repository)
    await db.commit()
