import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import SecretStore, secret_store
from app.models.account import Account
from app.models.membership import Membership, RoleEnum
from app.models.user import User
from app.services.auth import AuthService
from app.services.auth.exceptions import (
    OAuthEmailUnverifiedError,
    OAuthStateInvalidError,
)
from app.services.auth.oauth import (
    OAuthClient,
    OAuthProfile,
    create_oauth_state,
    verify_oauth_state,
)


@pytest.mark.asyncio
async def test_secret_store_text_encryption():
    """Test symmetric text encryption and decryption at rest."""
    store = SecretStore()
    raw_token = "gho_16C7e42F292c6912E7710c838347Ae178B4a"

    ciphertext = store.encrypt_text(raw_token)
    assert ciphertext != raw_token
    assert store.decrypt_text(ciphertext) == raw_token

    # Global secret_store behaves identically
    ct2 = secret_store.encrypt_text("google-access-token-12345")
    assert secret_store.decrypt_text(ct2) == "google-access-token-12345"


@pytest.mark.asyncio
async def test_oauth_state_verification():
    """Test cryptographic state token creation and validation."""
    state = create_oauth_state("github")
    # Should not raise for matching provider
    verify_oauth_state(state, "github")

    # Mismatched provider raises
    with pytest.raises(OAuthStateInvalidError):
        verify_oauth_state(state, "google")

    # Tampered state raises
    with pytest.raises(OAuthStateInvalidError):
        verify_oauth_state("invalid.tampered.token", "github")


@pytest.mark.asyncio
async def test_oauth_first_time_registration(db_session: AsyncSession):
    """Test first-time OAuth sign-in creates user, account, personal org, and owner membership."""
    profile = OAuthProfile(
        provider="github",
        provider_account_id=f"gh_{uuid.uuid4().hex[:8]}",
        email=f"new_gh_{uuid.uuid4().hex[:6]}@example.com",
        email_verified=True,
        name="GitHub Developer",
        avatar_url="https://avatars.githubusercontent.com/u/12345",
        access_token="gho_test_token_999",
        scopes="read:user,user:email",
        raw_metadata={"id": 12345, "login": "ghdev"},
    )

    user, token = await AuthService.link_or_create_oauth_user(db_session, profile)

    assert user.email == profile.email
    assert user.full_name == "GitHub Developer"
    assert user.avatar_url == profile.avatar_url
    assert user.hashed_password is None
    assert token is not None

    # Check Account record
    stmt_acc = select(Account).where(Account.user_id == user.id)
    acc = (await db_session.execute(stmt_acc)).scalar_one()
    assert acc.provider == "github"
    assert acc.provider_account_id == profile.provider_account_id
    assert secret_store.decrypt_text(acc.encrypted_access_token) == "gho_test_token_999"

    # Check personal Organization and Membership
    stmt_mem = select(Membership).where(Membership.user_id == user.id)
    mem = (await db_session.execute(stmt_mem)).scalar_one()
    assert mem.role == RoleEnum.OWNER


@pytest.mark.asyncio
async def test_oauth_account_linking_verified_email(db_session: AsyncSession):
    """Rule 1: If user exists with password, link OAuth account when email is verified."""
    email = f"shared_{uuid.uuid4().hex[:6]}@example.com"

    # 1. User signs up originally with password
    orig_user, _ = await AuthService.register(
        db_session,
        payload=type("Req", (), {"email": email, "password": "Password123!", "full_name": "Original Name", "org_name": None})(),
    )

    # 2. Later logs in with Google using the same verified email
    google_profile = OAuthProfile(
        provider="google",
        provider_account_id="google_sub_888",
        email=email,
        email_verified=True,
        name="Google Profile Name",
        avatar_url="https://lh3.googleusercontent.com/a/photo",
        access_token="ya29.test_google_token",
        scopes="openid,email,profile",
        raw_metadata={"sub": "google_sub_888"},
    )

    linked_user, _ = await AuthService.link_or_create_oauth_user(db_session, google_profile)

    # Reuses existing user ID (no duplicate accounts)
    assert linked_user.id == orig_user.id
    assert linked_user.email == email
    # User retains existing password
    assert linked_user.hashed_password is not None

    # Account record exists
    stmt_acc = select(Account).where(Account.user_id == orig_user.id)
    acc = (await db_session.execute(stmt_acc)).scalar_one()
    assert acc.provider == "google"
    assert acc.provider_account_id == "google_sub_888"


@pytest.mark.asyncio
async def test_oauth_account_linking_rejected_unverified_email(db_session: AsyncSession):
    """Rule 1: If provider email is unverified, refuse automatic linking to prevent hijacking."""
    email = f"victim_{uuid.uuid4().hex[:6]}@example.com"

    await AuthService.register(
        db_session,
        payload=type("Req", (), {"email": email, "password": "SecurePassword123!", "full_name": "Legit User", "org_name": None})(),
    )

    unverified_profile = OAuthProfile(
        provider="github",
        provider_account_id="attacker_gh_007",
        email=email,
        email_verified=False,  # Unverified!
        name="Attacker",
        avatar_url=None,
        access_token="gho_fake",
        scopes="read:user",
        raw_metadata={},
    )

    with pytest.raises(OAuthEmailUnverifiedError):
        await AuthService.link_or_create_oauth_user(db_session, unverified_profile)


@pytest.mark.asyncio
async def test_oauth_url_endpoint(client: AsyncClient):
    """Test GET /api/v1/auth/oauth/{provider}/url generates standard authorization parameters."""
    with patch.object(OAuthClient, "get_authorization_url", return_value="https://github.com/login/oauth/authorize?mock=1"):
        resp = await client.get("/api/v1/auth/oauth/github/url")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "github"
        assert "authorization_url" in data
        assert "state" in data


@pytest.mark.asyncio
async def test_oauth_exchange_endpoint(client: AsyncClient):
    """Test POST /api/v1/auth/oauth/exchange programmatically completes handshake."""
    state = create_oauth_state("github")
    mock_profile = OAuthProfile(
        provider="github",
        provider_account_id=f"gh_{uuid.uuid4().hex[:6]}",
        email=f"exchange_{uuid.uuid4().hex[:6]}@example.com",
        email_verified=True,
        name="Exchange User",
        avatar_url="https://avatar.url",
        access_token="gho_123",
        scopes="read:user",
        raw_metadata={},
    )

    with patch.object(OAuthClient, "exchange_code_for_profile", return_value=mock_profile):
        resp = await client.post(
            "/api/v1/auth/oauth/exchange",
            json={
                "provider": "github",
                "code": "test_code_123",
                "state": state,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == mock_profile.email
        assert data["user"]["full_name"] == "Exchange User"
        assert data["user"]["avatar_url"] == "https://avatar.url"
