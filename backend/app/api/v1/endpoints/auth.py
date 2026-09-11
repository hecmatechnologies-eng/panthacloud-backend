import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])


def generate_slug(text: str) -> str:
    """Convert text into a URL-friendly slug."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not clean:
        clean = "org"
    return f"{clean}-{uuid.uuid4().hex[:6]}"


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and initialize personal organization",
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    normalized_email = str(payload.email).strip().lower()

    # Reject duplicate email
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    # Hash password safely
    password_hash = hash_password(payload.password)

    # Transactional registration: User + Initial Organization + OWNER Membership
    user = User(
        email=normalized_email,
        hashed_password=password_hash,
        full_name=payload.full_name,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # Generate user.id

    org_name = payload.org_name or (f"{payload.full_name}'s Org" if payload.full_name else "Personal Organization")
    org_slug = generate_slug(org_name)

    org = Organization(
        name=org_name,
        slug=org_slug,
    )
    db.add(org)
    await db.flush()  # Generate org.id

    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=RoleEnum.OWNER,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=str(user.id))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT access token",
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    normalized_email = str(payload.email).strip().lower()

    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # Constant time / non-revealing error
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=str(user.id))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Retrieve profile of currently authenticated user",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return UserRead.model_validate(current_user)
