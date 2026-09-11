from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_current_contract,
    get_current_project,
    get_current_repository,
    get_current_snapshot,
    get_current_user,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.contract import ApiContract
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.models.user import User
from app.schemas.contract import (
    ApiContractRead,
    ApiOperationRead,
    ContractCreate,
)
from app.services.repository.contract import (
    ContractNormalizationError,
    DiscoveryRunNotFoundError,
    SnapshotNotReadyError,
    contract_service,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/contracts",
    tags=["Contracts"],
)


def to_contract_read(contract: ApiContract) -> ApiContractRead:
    return ApiContractRead(
        id=contract.id,
        snapshot_id=contract.snapshot_id,
        discovery_run_id=contract.discovery_run_id,
        status=contract.status,
        title=contract.title,
        version=contract.version,
        format=contract.format,
        servers=contract.servers or [],
        authentication=contract.authentication or [],
        schemas=contract.schemas or {},
        reconciliation=contract.reconciliation or {},
        metadata=contract.metadata_ or {},
        operations=[
            ApiOperationRead(
                id=op.id,
                contract_id=op.contract_id,
                method=op.method,
                path=op.path,
                operation_id=op.operation_id,
                summary=op.summary,
                description=op.description,
                source=op.source,
                source_file=op.source_file,
                source_line=op.source_line,
                authentication_required=op.authentication_required,
                request_schema=op.request_schema,
                response_schema=op.response_schema,
                tags=op.tags or [],
                evidence=op.evidence or {},
                created_at=op.created_at,
                updated_at=op.updated_at,
            )
            for op in (contract.operations or [])
        ],
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


@router.post(
    "",
    response_model=ApiContractRead,
    status_code=status.HTTP_201_CREATED,
    summary="Normalize API contracts and reconcile static routes for a snapshot",
)
async def normalize_contract(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CONTRACT_CREATE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: ContractCreate | None = None,
) -> ApiContractRead:
    org, _ = tenant

    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot normalize contract on snapshot with status '{snapshot.status.value}'. Status must be 'READY'.",
        )

    discovery_run_id = payload.discovery_run_id if payload else None

    try:
        contract = await contract_service.normalize_contract(
            db=db,
            organization_id=org.id,
            project_id=project.id,
            repository=repository,
            snapshot=snapshot,
            discovery_run_id=discovery_run_id,
            user_id=current_user.id,
        )
    except SnapshotNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except DiscoveryRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ContractNormalizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return to_contract_read(contract)


@router.get(
    "",
    response_model=list[ApiContractRead],
    summary="List normalized contracts for a snapshot",
)
async def list_contracts(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CONTRACT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiContractRead]:
    stmt = (
        select(ApiContract)
        .options(selectinload(ApiContract.operations))
        .where(ApiContract.snapshot_id == snapshot.id)
        .order_by(ApiContract.created_at.desc())
    )
    result = await db.execute(stmt)
    contracts = result.scalars().all()
    return [to_contract_read(c) for c in contracts]


@router.get(
    "/{contract_id}",
    response_model=ApiContractRead,
    summary="Retrieve a normalized contract by ID",
)
async def get_contract(
    contract: Annotated[ApiContract, Depends(get_current_contract)],
) -> ApiContractRead:
    return to_contract_read(contract)
