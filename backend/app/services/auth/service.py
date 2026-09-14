import re
import uuid

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth.exceptions import (
    CredentialsMissingError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)


def generate_slug(text: str) -> str:
    """Convert text into a URL-friendly slug."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not clean:
        clean = "org"
    return f"{clean}-{uuid.uuid4().hex[:6]}"


class AuthService:
    """Service encapsulating authentication, registration, and user token resolution."""

    @staticmethod
    async def register(db: AsyncSession, payload: RegisterRequest) -> tuple[User, str]:
        """Registers a new user, default personal organization, and initial OWNER membership."""
        normalized_email = str(payload.email).strip().lower()

        stmt = select(User).where(User.email == normalized_email)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise UserAlreadyExistsError(
                message="A user with this email address already exists.",
                field="email",
            )

        password_hash = hash_password(payload.password)

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
        return user, token

    @staticmethod
    async def authenticate(db: AsyncSession, payload: LoginRequest) -> tuple[User, str]:
        """Authenticates user credentials and generates a signed JWT token."""
        normalized_email = str(payload.email).strip().lower()

        stmt = select(User).where(User.email == normalized_email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not verify_password(payload.password, user.hashed_password):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        token = create_access_token(subject=str(user.id))
        return user, token

    @staticmethod
    async def resolve_user_from_token(db: AsyncSession, token: str | None) -> User:
        """Validates a JWT bearer token and returns the corresponding active user."""
        if not token:
            raise CredentialsMissingError()

        try:
            payload = decode_access_token(token)
            user_id_str: str | None = payload.get("sub")
            if not user_id_str:
                raise InvalidTokenError("Token payload missing subject identifier.")
            user_id = uuid.UUID(user_id_str)
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError()
        except (jwt.PyJWTError, ValueError):
            raise InvalidTokenError()

        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError()

        if not user.is_active:
            raise InactiveUserError()

        return user
