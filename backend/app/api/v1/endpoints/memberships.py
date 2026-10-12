import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.api.v1.endpoints._location import CREATED_RESPONSE, created
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.user import User
from app.schemas.membership import (
    MembershipCreate,
    MembershipRead,
    MembershipRoleUpdate,
)

router = APIRouter(prefix="/organizations/{org_id}/members", tags=["Memberships"])


@router.get(
    "",
    response_model=list[MembershipRead],
    summary="List all members in the organization",
)
async def list_members(
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.MEMBERS_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[MembershipRead]:
    org, _ = tenant
    stmt = (
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.organization_id == org.id)
        .order_by(Membership.created_at.asc())
    )
    result = await db.execute(stmt)
    memberships = result.scalars().all()
    return [MembershipRead.model_validate(m) for m in memberships]


@router.post(
    "",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
    responses=CREATED_RESPONSE,
    summary="Add a member directly to the organization (MVP simplification)",
)
async def add_member(
    payload: MembershipCreate,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.MEMBERS_INVITE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> MembershipRead:
    """
    MVP Simplification Note:
    Adds the user directly to the organization without an asynchronous email invite workflow,
    as permitted by the Phase 02 specification.
    """
    org, caller_membership = tenant
    normalized_email = str(payload.email).strip().lower()

    # Find target user
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with specified email does not exist.",
        )

    # Invariant: Membership uniqueness per (user_id, organization_id)
    stmt_exist = select(Membership).where(
        Membership.organization_id == org.id,
        Membership.user_id == target_user.id,
    )
    result_exist = await db.execute(stmt_exist)
    if result_exist.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this organization.",
        )

    # Admins cannot assign the OWNER role
    if caller_membership.role == RoleEnum.ADMIN and payload.role == RoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot assign the OWNER role.",
        )

    membership = Membership(
        user_id=target_user.id,
        organization_id=org.id,
        role=payload.role,
    )
    db.add(membership)
    await db.commit()

    # Re-fetch with user loaded for schema serialization
    stmt_load = (
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.id == membership.id)
    )
    result_load = await db.execute(stmt_load)
    saved_membership = result_load.scalar_one()

    created(response, "organizations", str(org.id), "members", str(saved_membership.id))
    return MembershipRead.model_validate(saved_membership)


@router.patch(
    "/{member_id}",
    response_model=MembershipRead,
    summary="Update a member's role (enforcing owner protection)",
)
async def update_member_role(
    member_id: uuid.UUID,
    payload: MembershipRoleUpdate,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.MEMBERS_ROLE_CHANGE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MembershipRead:
    org, _ = tenant

    stmt = select(Membership).where(
        Membership.id == member_id,
        Membership.organization_id == org.id,
    )
    result = await db.execute(stmt)
    target_membership = result.scalar_one_or_none()

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization.",
        )

    # Invariant: Last owner protection
    if target_membership.role == RoleEnum.OWNER and payload.role != RoleEnum.OWNER:
        count_stmt = select(func.count(Membership.id)).where(
            Membership.organization_id == org.id,
            Membership.role == RoleEnum.OWNER,
        )
        owner_count_res = await db.execute(count_stmt)
        owner_count = owner_count_res.scalar_one()
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last OWNER. An organization must have at least one OWNER.",
            )

    target_membership.role = payload.role
    await db.commit()

    stmt_load = (
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.id == target_membership.id)
    )
    result_load = await db.execute(stmt_load)
    saved_membership = result_load.scalar_one()

    return MembershipRead.model_validate(saved_membership)


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the organization (enforcing owner protection)",
)
async def remove_member(
    member_id: uuid.UUID,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.MEMBERS_REMOVE)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    org, caller_membership = tenant

    stmt = select(Membership).where(
        Membership.id == member_id,
        Membership.organization_id == org.id,
    )
    result = await db.execute(stmt)
    target_membership = result.scalar_one_or_none()

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization.",
        )

    # Rule: ADMIN cannot remove an OWNER
    if caller_membership.role == RoleEnum.ADMIN and target_membership.role == RoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot remove an organization OWNER.",
        )

    # Invariant: Last owner protection
    if target_membership.role == RoleEnum.OWNER:
        count_stmt = select(func.count(Membership.id)).where(
            Membership.organization_id == org.id,
            Membership.role == RoleEnum.OWNER,
        )
        owner_count_res = await db.execute(count_stmt)
        owner_count = owner_count_res.scalar_one()
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last OWNER. An organization must have at least one OWNER.",
            )

    await db.delete(target_membership)
    await db.commit()
