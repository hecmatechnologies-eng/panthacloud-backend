from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_integration_plan,
    get_current_project,
    get_current_repository,
    get_current_snapshot,
    get_current_user,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.integration_plan import IntegrationPlan
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.models.user import User
from app.schemas.integration_plan import (
    IntegrationCandidate,
    IntegrationPlanCreate,
    IntegrationPlanRead,
    RequiredCredential,
    UnresolvedQuestion,
)
from app.services.repository.integration_planner import (
    DiscoveryRunNotFoundError,
    IntegrationPlanningError,
    SnapshotNotReadyError,
    integration_planning_service,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/integration-plans",
    tags=["Integration Plans"],
)


def to_plan_read(plan: IntegrationPlan) -> IntegrationPlanRead:
    return IntegrationPlanRead(
        id=plan.id,
        project_id=plan.project_id,
        snapshot_id=plan.snapshot_id,
        contract_id=plan.contract_id,
        status=plan.status,
        candidates=[IntegrationCandidate(**c) for c in (plan.candidates or [])],
        required_credentials=[RequiredCredential(**rc) for rc in (plan.required_credentials or [])],
        unresolved_questions=[UnresolvedQuestion(**uq) for uq in (plan.unresolved_questions or [])],
        evidence=plan.evidence or {},
        metadata=plan.metadata_ or {},
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post(
    "",
    response_model=IntegrationPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate evidence-backed integration plan for a snapshot",
)
async def create_integration_plan(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_PLAN_CREATE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: IntegrationPlanCreate | None = None,
) -> IntegrationPlanRead:
    org, _ = tenant

    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate integration plan on snapshot with status '{snapshot.status.value}'. Status must be 'READY'.",
        )

    contract_id = payload.contract_id if payload else None

    try:
        plan = await integration_planning_service.generate_plan(
            db=db,
            organization_id=org.id,
            project_id=project.id,
            repository=repository,
            snapshot=snapshot,
            contract_id=contract_id,
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
    except IntegrationPlanningError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return to_plan_read(plan)


@router.get(
    "",
    response_model=list[IntegrationPlanRead],
    summary="List integration plans for a snapshot",
)
async def list_integration_plans(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_PLAN_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IntegrationPlanRead]:
    stmt = (
        select(IntegrationPlan)
        .where(IntegrationPlan.snapshot_id == snapshot.id)
        .order_by(IntegrationPlan.created_at.desc())
    )
    result = await db.execute(stmt)
    plans = result.scalars().all()
    return [to_plan_read(p) for p in plans]


@router.get(
    "/{plan_id}",
    response_model=IntegrationPlanRead,
    summary="Retrieve an integration plan by ID",
)
async def get_integration_plan(
    plan: Annotated[IntegrationPlan, Depends(get_current_integration_plan)],
) -> IntegrationPlanRead:
    return to_plan_read(plan)
