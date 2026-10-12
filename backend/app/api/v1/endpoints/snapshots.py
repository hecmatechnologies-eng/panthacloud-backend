from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_project,
    get_current_repository,
    get_current_snapshot,
    get_current_user,
    require_permission,
)
from app.api.v1.endpoints._location import CREATED_RESPONSE, created
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.integration import Integration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository, RepositoryStatus
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.models.user import User
from app.schemas.repository_snapshot import (
    InspectionResult,
    SnapshotCreate,
    SnapshotRead,
)
from app.services.repository.acquisition import acquisition_service
from app.services.repository.inspection import inspection_service

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots",
    tags=["Snapshots"],
)


def to_snapshot_read(snapshot: RepositorySnapshot) -> SnapshotRead:
    return SnapshotRead(
        id=snapshot.id,
        repository_id=snapshot.repository_id,
        branch=snapshot.branch,
        commit_sha=snapshot.commit_sha,
        status=snapshot.status,
        acquired_at=snapshot.acquired_at,
        completed_at=snapshot.completed_at,
        error_code=snapshot.error_code,
        error_message=snapshot.error_message,
        metadata=snapshot.metadata_,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


@router.post(
    "",
    response_model=SnapshotRead,
    status_code=status.HTTP_201_CREATED,
    responses=CREATED_RESPONSE,
    summary="Acquire a new repository snapshot revision into an isolated workspace",
)
async def create_snapshot(
    payload: SnapshotCreate,
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_SNAPSHOT_CREATE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> SnapshotRead:
    org, _ = tenant

    if repository.status == RepositoryStatus.DISCONNECTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot acquire snapshot for a disconnected repository.",
        )

    stmt = select(Integration).where(Integration.id == repository.integration_id)
    result = await db.execute(stmt)
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository integration not found.",
        )

    # Allocate initial snapshot record
    snapshot = RepositorySnapshot(
        repository_id=repository.id,
        branch=payload.branch,
        status=SnapshotStatus.PENDING,
        metadata_={},
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    # Record audit event
    await acquisition_service.record_audit(
        db,
        organization_id=org.id,
        project_id=project.id,
        user_id=current_user.id,
        event_type="repository.snapshot.created",
        resource_id=snapshot.id,
        payload={"branch": snapshot.branch},
    )
    await db.commit()

    # Trigger shallow Git acquisition into isolated workspace
    snapshot = await acquisition_service.acquire(
        db=db,
        organization_id=org.id,
        project_id=project.id,
        snapshot=snapshot,
        repository=repository,
        integration=integration,
        user_id=current_user.id,
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
    )
    return to_snapshot_read(snapshot)


@router.get(
    "",
    response_model=list[SnapshotRead],
    summary="List all acquired snapshots for a repository",
)
async def list_snapshots(
    repository: Annotated[Repository, Depends(get_current_repository)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_SNAPSHOT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SnapshotRead]:
    stmt = (
        select(RepositorySnapshot)
        .where(RepositorySnapshot.repository_id == repository.id)
        .order_by(RepositorySnapshot.created_at.desc())
    )
    result = await db.execute(stmt)
    snapshots = result.scalars().all()
    return [to_snapshot_read(s) for s in snapshots]


@router.get(
    "/{snapshot_id}",
    response_model=SnapshotRead,
    summary="Retrieve safe snapshot metadata and acquisition status",
)
async def get_snapshot(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
) -> SnapshotRead:
    return to_snapshot_read(snapshot)


@router.post(
    "/{snapshot_id}/inspect",
    response_model=InspectionResult,
    summary="Perform deterministic, read-only inspection of the snapshot workspace",
)
async def inspect_snapshot(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.REPOSITORY_INSPECT)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InspectionResult:
    org, _ = tenant

    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot inspect snapshot with status '{snapshot.status.value}'. Status must be 'READY'.",
        )

    try:
        inspection_data = await inspection_service.inspect(
            db=db,
            organization_id=org.id,
            project_id=project.id,
            repository=repository,
            snapshot=snapshot,
            user_id=current_user.id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return InspectionResult(**inspection_data)
