from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_execution_plan,
    get_current_project,
    get_current_repository,
    get_current_snapshot,
    get_current_user,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.execution_plan import ExecutionPlan
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.models.repository import Repository
from app.models.repository_snapshot import RepositorySnapshot, SnapshotStatus
from app.models.user import User
from app.schemas.execution_plan import (
    ExecutionPlanCreate,
    ExecutionPlanRead,
    ExecutionStep,
)
from app.services.repository.execution_planner import (
    ExecutionPlanningError,
    execution_planning_service,
)
from app.services.repository.integration_adapter import (
    IntegrationPlanNotFoundError,
    SnapshotNotReadyError,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/execution-plans",
    tags=["Execution Plans"],
)


def to_plan_read(plan: ExecutionPlan) -> ExecutionPlanRead:
    return ExecutionPlanRead(
        id=plan.id,
        project_id=plan.project_id,
        snapshot_id=plan.snapshot_id,
        integration_plan_id=plan.integration_plan_id,
        status=plan.status,
        steps=[ExecutionStep(**s) for s in (plan.steps or [])],
        required_credentials=plan.required_credentials or [],
        prerequisites=plan.prerequisites or [],
        approval_requirements=plan.approval_requirements or [],
        blocked_reasons=plan.blocked_reasons or [],
        evidence=plan.evidence or {},
        metadata=plan.metadata_ or {},
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post(
    "",
    response_model=ExecutionPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate declarative execution plan for a snapshot",
)
async def create_execution_plan(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    repository: Annotated[Repository, Depends(get_current_repository)],
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.EXECUTION_PLAN_CREATE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: ExecutionPlanCreate | None = None,
) -> ExecutionPlanRead:
    org, _ = tenant

    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot generate execution plan on snapshot with status '{snapshot.status.value}'. Status must be 'READY'.",
        )

    plan_id = payload.integration_plan_id if payload else None

    try:
        plan = await execution_planning_service.generate_execution_plan(
            db=db,
            organization_id=org.id,
            project_id=project.id,
            repository=repository,
            snapshot=snapshot,
            integration_plan_id=plan_id,
            user_id=current_user.id,
        )
        return to_plan_read(plan)
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
    except ExecutionPlanningError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution planning failed: {e!s}",
        ) from e


@router.get(
    "",
    response_model=list[ExecutionPlanRead],
    status_code=status.HTTP_200_OK,
    summary="List execution plans for a snapshot",
)
async def list_execution_plans(
    snapshot: Annotated[RepositorySnapshot, Depends(get_current_snapshot)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.EXECUTION_PLAN_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ExecutionPlanRead]:
    stmt = (
        select(ExecutionPlan)
        .where(ExecutionPlan.snapshot_id == snapshot.id)
        .order_by(ExecutionPlan.created_at.desc())
    )
    result = await db.execute(stmt)
    plans = result.scalars().all()
    return [to_plan_read(p) for p in plans]


@router.get(
    "/{plan_id}",
    response_model=ExecutionPlanRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a specific execution plan",
)
async def get_execution_plan(
    plan: Annotated[ExecutionPlan, Depends(get_current_execution_plan)],
) -> ExecutionPlanRead:
    return to_plan_read(plan)
