import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.slugs import slugify
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationRead

logger = logging.getLogger("fussion.organizations")

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization and establish OWNER membership",
)
async def create_organization(
    payload: OrganizationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationRead:
    slug = payload.slug or f"{slugify(payload.name, 'org')}-{uuid.uuid4().hex[:6]}"

    # Check slug uniqueness
    stmt = select(Organization).where(Organization.slug == slug)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization slug '{slug}' is already in use.",
        )

    org = Organization(name=payload.name, slug=slug)
    db.add(org)
    await db.flush()

    membership = Membership(
        user_id=current_user.id,
        organization_id=org.id,
        role=RoleEnum.OWNER,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(org)

    return OrganizationRead.model_validate(org)


@router.get(
    "",
    response_model=list[OrganizationRead],
    summary="List all organizations where current user holds membership",
)
async def list_organizations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationRead]:
    stmt = (
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == current_user.id)
        .order_by(Organization.created_at.desc())
    )
    result = await db.execute(stmt)
    orgs = result.scalars().all()
    return [OrganizationRead.model_validate(org) for org in orgs]


@router.get(
    "/{org_id}",
    response_model=OrganizationRead,
    summary="Retrieve organization by ID within tenant scope",
)
async def get_organization(
    tenant: Annotated[tuple[Organization, Membership], Depends(get_current_organization)],
) -> OrganizationRead:
    org, _ = tenant
    return OrganizationRead.model_validate(org)


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an organization and everything it owns",
)
async def delete_organization(
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.ORG_DELETE)),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete the organization, cascading to its memberships, projects and everything beneath them.

    Only an OWNER holds `ORG_DELETE`, and a foreign or unknown organization is a 404 from
    `get_current_organization` before this runs — the same anti-enumeration answer every other
    tenant-scoped route gives.

    The deletion is **logged, not audited**. An audit event would be deleted with the organization:
    `audit_events.organization_id` is a cascading foreign key, so the record of the deletion cannot
    outlive the thing deleted. A durable record of organization deletion needs an audit store that
    does not cascade — deliberately not invented here.
    """
    org, _ = tenant

    logger.warning(
        "Organization %s (%s) deleted by user %s", org.id, org.slug, current_user.id
    )

    await db.delete(org)
    await db.commit()
