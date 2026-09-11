from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_integration_adapter,
    get_current_project,
    get_current_repository,
    get_current_snapshot,
    get_current_user,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.integration_adapter import IntegrationAdapter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.models.user import User
from app.schemas.integration_adapter import (
    AdapterOperation,
    IntegrationAdapterCreate,
    IntegrationAdapterRead,
)
from app.services.repository.integration_adapter import (
    IntegrationAdapterPlanningError,
    IntegrationPlanNotFoundError,
    SnapshotNotReadyError,
    integration_adapter_service,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/integration-adapters",
    tags=["Integration Adapters"],
)


def to_adapter_read(adapter: IntegrationAdapter) -> IntegrationAdapterRead:
    return IntegrationAdapterRead(
        id=adapter.id,
        integration_plan_id=adapter.integration_plan_id,
        snapshot_id=adapter.snapshot_id,
        name=adapter.name,
        adapter_type=adapter.adapter_type,
        provider=adapter.provider,
        status=adapter.status,
        description=adapter.description,
        configuration=adapter.configuration or {},
        required_credentials=adapter.required_credentials or [],
        operations=[AdapterOperation(**op) for op in (adapter.operations or [])],
        prerequisites=adapter.prerequisites or [],
        constraints=adapter.constraints or [],
        evidence=adapter.evidence or {},
        metadata=adapter.metadata_ or {},
        created_at=adapter.created_at,
        updated_at=adapter.updated_at,
    )


@router.post(
    "",
    response_model=list[IntegrationAdapterRead],
    status_code=status.HTTP_201_CREATED,
    summary="Generate evidence-backed integration adapters for a snapshot",
)
async def create_integration_adapters(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_ADAPTER_CREATE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: IntegrationAdapterCreate | None = None,
) -> list[IntegrationAdapterRead]:
    org, _ = tenant

    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate integration adapters on snapshot with status '{snapshot.status.value}'. Status must be 'READY'.",
        )

    plan_id = payload.integration_plan_id if payload else None

    try:
        adapters = await integration_adapter_service.generate_adapters(
            db=db,
            organization_id=org.id,
            project_id=project.id,
            repository=repository,
            snapshot=snapshot,
            integration_plan_id=plan_id,
            user_id=current_user.id,
        )
        return [to_adapter_read(a) for a in adapters]
    except SnapshotNotReadyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except IntegrationPlanNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except IntegrationAdapterPlanningError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Adapter planning failed: {e!s}",
        ) from e


@router.get(
    "",
    response_model=list[IntegrationAdapterRead],
    status_code=status.HTTP_200_OK,
    summary="List integration adapters for a snapshot",
)
async def list_integration_adapters(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_ADAPTER_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IntegrationAdapterRead]:
    stmt = (
        select(IntegrationAdapter)
        .where(IntegrationAdapter.snapshot_id == snapshot.id)
        .order_by(IntegrationAdapter.adapter_type, IntegrationAdapter.name)
    )
    result = await db.execute(stmt)
    adapters = result.scalars().all()
    return [to_adapter_read(a) for a in adapters]


@router.get(
    "/{adapter_id}",
    response_model=IntegrationAdapterRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a specific integration adapter",
)
async def get_integration_adapter(
    adapter: Annotated[IntegrationAdapter, Depends(get_current_integration_adapter)],
) -> IntegrationAdapterRead:
    return to_adapter_read(adapter)
