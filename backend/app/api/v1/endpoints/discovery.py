from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_discovery,
    get_current_project,
    get_current_repository,
    get_current_snapshot,
    get_current_user,
    require_permission,
)
from app.api.v1.endpoints._location import CREATED_RESPONSE, created
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.discovery import DiscoveryRun
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.models.user import User
from app.schemas.discovery import DiscoveryRead
from app.services.repository.discovery import SnapshotNotReadyError, discovery_service

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/discoveries",
    tags=["Discovery"],
)


def to_discovery_read(run: DiscoveryRun) -> DiscoveryRead:
    return DiscoveryRead(
        id=run.id,
        snapshot_id=run.snapshot_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_code=run.error_code,
        error_message=run.error_message,
        metadata=run.metadata_ or {},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.post(
    "",
    response_model=DiscoveryRead,
    status_code=status.HTTP_201_CREATED,
    responses=CREATED_RESPONSE,
    summary="Trigger deterministic contract & architecture discovery on a snapshot",
)
async def create_discovery(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_DISCOVERY_CREATE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> DiscoveryRead:
    org, _ = tenant

    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot run discovery on snapshot with status '{snapshot.status.value}'. Status must be 'READY'.",
        )

    try:
        run = await discovery_service.run_discovery(
            db=db,
            organization_id=org.id,
            project_id=project.id,
            repository=repository,
            snapshot=snapshot,
            user_id=current_user.id,
        )
    except SnapshotNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    created(
        response,
        "organizations",
        str(org.id),
        "projects",
        str(project.id),
        "repositories",
        str(repository.id),
        "snapshots",
        str(snapshot.id),
        "discoveries",
        str(run.id),
    )
    return to_discovery_read(run)


@router.get(
    "",
    response_model=list[DiscoveryRead],
    summary="List all discovery runs for a snapshot",
)
async def list_discoveries(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_DISCOVERY_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DiscoveryRead]:
    stmt = (
        select(DiscoveryRun)
        .where(DiscoveryRun.snapshot_id == snapshot.id)
        .order_by(DiscoveryRun.created_at.desc())
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [to_discovery_read(r) for r in runs]


@router.get(
    "/{discovery_id}",
    response_model=DiscoveryRead,
    summary="Retrieve discovery run findings and architectural fact model",
)
async def get_discovery(
    discovery: Annotated[DiscoveryRun, Depends(get_current_discovery)],
) -> DiscoveryRead:
    return to_discovery_read(discovery)
