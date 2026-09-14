"""Read-only agent-run and model-usage endpoints (FR-073, FR-089, FR-090, FR-116).

These are the Studio's run-cockpit surface: what the harness recorded for a project's agent runs,
and what its model calls cost. Tenancy is resolved by ``get_current_project`` before any query, so a
run belonging to another project — or another tenant — is a 404, never a 403 (anti-enumeration).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_project, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.agent_run import AgentRun
from app.models.membership import Membership
from app.models.model_usage import ModelUsage
from app.models.organization import Organization
from app.models.project import Project
from app.schemas.agent_run import (
    AgentRunRead,
    AgentRunSummaryRead,
    BudgetStatus,
    ModelUsageByModel,
    ModelUsageSummary,
)

router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/agent-runs",
    tags=["Agent Runs"],
)
usage_router = APIRouter(
    prefix="/organizations/{org_id}/projects/{project_id}/usage",
    tags=["Usage"],
)
budget_router = APIRouter(
    prefix="/organizations/{org_id}/usage",
    tags=["Usage"],
)


@router.get("", response_model=list[AgentRunSummaryRead], summary="List agent runs for a project")
async def list_agent_runs(
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentRunSummaryRead]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.project_id == project.id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = (await db.execute(stmt)).scalars().all()
    return [AgentRunSummaryRead.model_validate(run) for run in runs]


@router.get("/{run_id}", response_model=AgentRunRead, summary="Retrieve one agent run with its tool log")
async def get_agent_run(
    run_id: uuid.UUID,
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentRunRead:
    stmt = (
        select(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.project_id == project.id)
        .options(selectinload(AgentRun.tool_calls))
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent run not found.",
        )
    return AgentRunRead.model_validate(run)


@usage_router.get("", response_model=ModelUsageSummary, summary="Model usage and cost for a project")
async def get_project_usage(
    project: Annotated[Project, Depends(get_current_project)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.PROJECT_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    integration_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ModelUsageSummary:
    conditions = [ModelUsage.project_id == project.id]
    if integration_id is not None:
        conditions.append(ModelUsage.integration_id == integration_id)

    totals_stmt = select(
        func.count(ModelUsage.id),
        func.coalesce(func.sum(ModelUsage.input_tokens), 0),
        func.coalesce(func.sum(ModelUsage.output_tokens), 0),
        func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0),
    ).where(*conditions)
    total_calls, input_tokens, output_tokens, cost_usd = (await db.execute(totals_stmt)).one()

    by_model_stmt = (
        select(
            ModelUsage.provider,
            ModelUsage.model,
            func.count(ModelUsage.id),
            func.coalesce(func.sum(ModelUsage.input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.output_tokens), 0),
            func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0),
        )
        .where(*conditions)
        .group_by(ModelUsage.provider, ModelUsage.model)
        .order_by(func.sum(ModelUsage.estimated_cost_usd).desc())
    )
    by_model = [
        ModelUsageByModel(
            provider=provider,
            model=model,
            calls=calls,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=Decimal(str(cost)),
        )
        for provider, model, calls, in_tokens, out_tokens, cost in (await db.execute(by_model_stmt)).all()
    ]

    return ModelUsageSummary(
        total_calls=int(total_calls or 0),
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        cost_usd=Decimal(str(cost_usd or 0)),
        by_model=by_model,
    )


@budget_router.get(
    "/budget",
    response_model=BudgetStatus,
    summary="Organization model-spend budget status (FR-074)",
)
async def get_org_budget(
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ORG_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BudgetStatus:
    org, _ = tenant
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    spend_stmt = select(func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0)).where(
        ModelUsage.organization_id == org.id,
        ModelUsage.created_at >= month_start,
    )
    spend = Decimal(str((await db.execute(spend_stmt)).scalar_one()))

    warning = settings.MODEL_BUDGET_WARNING_FRACTION
    throttle = settings.MODEL_BUDGET_THROTTLE_FRACTION
    raw_limit = settings.MODEL_DEFAULT_SPEND_LIMIT_USD

    if raw_limit is None:
        return BudgetStatus(
            limit_usd=None,
            month_spend_usd=spend,
            fraction=None,
            state="uncapped",
            warning_fraction=warning,
            throttle_fraction=throttle,
        )

    limit = Decimal(str(raw_limit))
    if limit <= 0:
        return BudgetStatus(
            limit_usd=limit,
            month_spend_usd=spend,
            fraction=1.0,
            state="suspended",
            warning_fraction=warning,
            throttle_fraction=throttle,
        )

    ratio = spend / limit
    if ratio >= 1:
        state = "suspended"
    elif ratio >= Decimal(str(throttle)):
        state = "throttled"
    elif ratio >= Decimal(str(warning)):
        state = "warning"
    else:
        state = "ok"

    return BudgetStatus(
        limit_usd=limit,
        month_spend_usd=spend,
        fraction=float(ratio),
        state=state,
        warning_fraction=warning,
        throttle_fraction=throttle,
    )
