import re
import uuid

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import secret_store
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.account import Account
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth.exceptions import (
    CredentialsMissingError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    OAuthEmailUnverifiedError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.services.auth.oauth import OAuthProfile


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

    @classmethod
    async def link_or_create_oauth_user(
        cls,
        db: AsyncSession,
        profile: OAuthProfile,
    ) -> tuple[User, str]:
        """
        Account Linking & OAuth Identity Resolution (Rule 1 & Rule 3):
        - If Account with (provider, provider_account_id) exists:
          Update tokens/metadata and return user.
        - If User with email exists:
          Only link if profile.email_verified is True.
          Create Account record referencing existing user.
        - If neither exists:
          Create new User (hashed_password=None, avatar_url=profile.avatar_url).
          Create Account record with encrypted access token.
          Initialize personal organization and OWNER membership.
        - Returns (user, session_jwt).
        """
        normalized_email = profile.email.strip().lower()

        # 1. Encrypt token at rest if provided
        encrypted_token = (
            secret_store.encrypt_text(profile.access_token)
            if profile.access_token
            else None
        )

        # 2. Check if this exact OAuth account is already connected
        stmt_account = select(Account).where(
            Account.provider == profile.provider,
            Account.provider_account_id == profile.provider_account_id,
        )
        result_account = await db.execute(stmt_account)
        account = result_account.scalar_one_or_none()

        if account:
            # Existing linked account: update access token / metadata
            account.encrypted_access_token = encrypted_token or account.encrypted_access_token
            account.scopes = profile.scopes or account.scopes
            account.profile_metadata = profile.raw_metadata

            stmt_user = select(User).where(User.id == account.user_id)
            result_user = await db.execute(stmt_user)
            user = result_user.scalar_one()

            if not user.is_active:
                raise InactiveUserError()

            if not user.avatar_url and profile.avatar_url:
                user.avatar_url = profile.avatar_url

            await db.commit()
            await db.refresh(user)

            token = create_access_token(subject=str(user.id))
            return user, token

        # 3. Account not found: Check if a user with this email exists
        stmt_user_email = select(User).where(User.email == normalized_email)
        result_user_email = await db.execute(stmt_user_email)
        existing_user = result_user_email.scalar_one_or_none()

        if existing_user:
            # Rule 1: Only link if provider explicitly states email is verified
            if not profile.email_verified:
                raise OAuthEmailUnverifiedError(
                    f"Cannot link {profile.provider.title()} account to existing user: email is not verified."
                )

            if not existing_user.is_active:
                raise InactiveUserError()

            # Create new Account connection linked to existing user
            new_account = Account(
                user_id=existing_user.id,
                provider=profile.provider,
                provider_account_id=profile.provider_account_id,
                encrypted_access_token=encrypted_token,
                scopes=profile.scopes,
                profile_metadata=profile.raw_metadata,
            )
            db.add(new_account)

            if not existing_user.avatar_url and profile.avatar_url:
                existing_user.avatar_url = profile.avatar_url

            await db.commit()
            await db.refresh(existing_user)

            token = create_access_token(subject=str(existing_user.id))
            return existing_user, token

        # 4. First-time registration via OAuth: Create user + account + personal organization
        new_user = User(
            email=normalized_email,
            hashed_password=None,
            full_name=profile.name,
            avatar_url=profile.avatar_url,
            is_active=True,
        )
        db.add(new_user)
        await db.flush()  # Generate new_user.id

        new_account = Account(
            user_id=new_user.id,
            provider=profile.provider,
            provider_account_id=profile.provider_account_id,
            encrypted_access_token=encrypted_token,
            scopes=profile.scopes,
            profile_metadata=profile.raw_metadata,
        )
        db.add(new_account)

        org_name = (f"{profile.name}'s Org" if profile.name else "Personal Organization")
        org_slug = generate_slug(org_name)

        org = Organization(
            name=org_name,
            slug=org_slug,
        )
        db.add(org)
        await db.flush()  # Generate org.id

        membership = Membership(
            user_id=new_user.id,
            organization_id=org.id,
            role=RoleEnum.OWNER,
        )
        db.add(membership)

        await db.commit()
        await db.refresh(new_user)

        token = create_access_token(subject=str(new_user.id))
        return new_user, token
