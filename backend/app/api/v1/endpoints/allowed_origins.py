"""Allowed origins for a website integration's public key (FR-107).

Management only: nothing checks a request's ``Origin`` against these until the tenant resolver
(step B2) exists.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_website_integration,
    require_permission,
)
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.allowed_origin import AllowedOrigin
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.website_integration import WebsiteIntegration
from app.schemas.website_integration import AllowedOriginCreate, AllowedOriginRead
from app.services.audit import record_audit

MAX_ORIGINS_PER_INTEGRATION = 20

router = APIRouter(
    tags=["Website Integrations"],
)


@router.get(
    "",
    response_model=list[AllowedOriginRead],
    summary="List the origins allowed to use this integration's public key",
)
async def list_allowed_origins(
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AllowedOriginRead]:
    stmt = (
        select(AllowedOrigin)
        .where(AllowedOrigin.integration_id == integration.id)
        .order_by(AllowedOrigin.created_at, AllowedOrigin.id)
    )
    origins = (await db.execute(stmt)).scalars().all()
    return [AllowedOriginRead.model_validate(o) for o in origins]


@router.post(
    "",
    response_model=AllowedOriginRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an origin allowed to use this integration's public key",
)
async def add_allowed_origin(
    payload: AllowedOriginCreate,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_UPDATE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AllowedOriginRead:
    # payload.origin is already canonical: AllowedOriginCreate normalises it.
    existing_stmt = select(AllowedOrigin.origin).where(
        AllowedOrigin.integration_id == integration.id
    )
    existing = set((await db.execute(existing_stmt)).scalars().all())
    if payload.origin in existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{payload.origin} is already registered for this integration.",
        )
    if len(existing) >= MAX_ORIGINS_PER_INTEGRATION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An integration can have at most {MAX_ORIGINS_PER_INTEGRATION} origins. "
                "Remove one before adding another."
            ),
        )

    allowed = AllowedOrigin(integration_id=integration.id, origin=payload.origin)
    db.add(allowed)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent request registered the same origin first.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{payload.origin} is already registered for this integration.",
        ) from None
    await db.refresh(allowed)

    await record_audit(
        db,
        tenant[0].id,
        integration.project_id,
        user.id,
        "integration.origin.added",
        integration.id,
        {"origin": allowed.origin},
    )
    return AllowedOriginRead.model_validate(allowed)


@router.delete(
    "/{origin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an allowed origin",
)
async def remove_allowed_origin(
    origin_id: uuid.UUID,
    integration: Annotated[WebsiteIntegration, Depends(get_current_website_integration)],
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.INTEGRATION_UPDATE)),
    ],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    stmt = select(AllowedOrigin).where(
        AllowedOrigin.id == origin_id,
        AllowedOrigin.integration_id == integration.id,
    )
    allowed = (await db.execute(stmt)).scalar_one_or_none()
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allowed origin not found for this integration.",
        )

    # Recorded before the delete, as delete_website_integration does: removing an origin is the
    # security-relevant half of this pair, and must not be able to happen unrecorded.
    await record_audit(
        db,
        tenant[0].id,
        integration.project_id,
        user.id,
        "integration.origin.removed",
        integration.id,
        {"origin": allowed.origin},
    )

    await db.delete(allowed)
    await db.commit()
