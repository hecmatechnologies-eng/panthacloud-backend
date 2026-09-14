import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings
from app.services.auth.exceptions import (
    OAuthEmailUnverifiedError,
    OAuthError,
    OAuthProviderError,
    OAuthStateInvalidError,
)

logger = logging.getLogger("fussion.oauth")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    provider_account_id: str
    email: str
    email_verified: bool
    name: str | None
    avatar_url: str | None
    access_token: str | None
    scopes: str | None
    raw_metadata: dict[str, Any]


def create_oauth_state(provider: str) -> str:
    """Generate a cryptographically signed state parameter to prevent CSRF attacks."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.OAUTH_STATE_EXPIRE_MINUTES)
    payload = {
        "provider": provider,
        "nonce": secrets.token_hex(16),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.effective_jwt_secret_key,
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_oauth_state(state: str | None, expected_provider: str) -> None:
    """Verify state token integrity and matching provider."""
    if not state:
        raise OAuthStateInvalidError("Missing OAuth state parameter.")

    try:
        payload = jwt.decode(
            state,
            settings.effective_jwt_secret_key,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        logger.warning("OAuth state verification failed: %s", exc)
        raise OAuthStateInvalidError("Invalid or expired OAuth state parameter.") from exc

    if payload.get("provider") != expected_provider:
        raise OAuthStateInvalidError("OAuth state provider mismatch.")


class OAuthClient:
    """Handles external OAuth2 handshakes with GitHub and Google."""

    @staticmethod
    def is_provider_configured(provider: str) -> bool:
        if provider == "github":
            return bool(
                settings.GITHUB_OAUTH_CLIENT_ID
                or settings.GITHUB_APP_CLIENT_ID
            )
        if provider == "google":
            return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)
        return False

    @classmethod
    def get_authorization_url(cls, provider: str, redirect_uri: str, state: str) -> str:
        """Construct the official provider authorization URL with PKCE / CSRF parameters."""
        if provider == "github":
            client_id = settings.GITHUB_OAUTH_CLIENT_ID or settings.GITHUB_APP_CLIENT_ID
            if not client_id:
                raise OAuthProviderError("GitHub OAuth is not configured on the server.")
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "read:user user:email",
                "state": state,
            }
            return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

        if provider == "google":
            if not settings.GOOGLE_OAUTH_CLIENT_ID:
                raise OAuthProviderError("Google OAuth is not configured on the server.")
            params = {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "offline",
                "prompt": "select_account",
            }
            return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

        raise OAuthError(f"Unsupported OAuth provider: '{provider}'")

    @classmethod
    async def exchange_code_for_profile(
        cls,
        provider: str,
        code: str,
        redirect_uri: str,
    ) -> OAuthProfile:
        """Exchange the authorization code for tokens and fetch verified user identity."""
        if provider == "github":
            return await cls._exchange_github(code, redirect_uri)
        if provider == "google":
            return await cls._exchange_google(code, redirect_uri)
        raise OAuthError(f"Unsupported OAuth provider: '{provider}'")

    @classmethod
    async def _exchange_github(cls, code: str, redirect_uri: str) -> OAuthProfile:
        client_id = settings.GITHUB_OAUTH_CLIENT_ID or settings.GITHUB_APP_CLIENT_ID
        client_secret = settings.GITHUB_OAUTH_CLIENT_SECRET or settings.GITHUB_APP_CLIENT_SECRET
        if not client_id or not client_secret:
            raise OAuthProviderError("GitHub OAuth credentials are not configured on the server.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Exchange authorization code for access token
            token_resp = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            if not token_resp.is_success:
                logger.error("GitHub token exchange failed: %s", token_resp.text)
                raise OAuthProviderError("Failed to exchange authorization code with GitHub.")

            token_data = token_resp.json()
            if "error" in token_data:
                err_desc = token_data.get("error_description", token_data["error"])
                logger.error("GitHub returned token error: %s", err_desc)
                raise OAuthProviderError(f"GitHub authorization failed: {err_desc}")

            access_token = token_data.get("access_token")
            scopes = token_data.get("scope")

            # 2. Fetch user profile
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Fussion-OAuth",
            }
            user_resp = await client.get(GITHUB_USER_URL, headers=headers)
            if not user_resp.is_success:
                raise OAuthProviderError("Failed to fetch user profile from GitHub.")
            user_data = user_resp.json()

            provider_account_id = str(user_data["id"])
            name = user_data.get("name") or user_data.get("login")
            avatar_url = user_data.get("avatar_url")

            # 3. Fetch primary verified email
            email = user_data.get("email")
            email_verified = False

            emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers)
            if emails_resp.is_success:
                emails_data = emails_resp.json()
                for item in emails_data:
                    if item.get("primary") and item.get("verified"):
                        email = item.get("email")
                        email_verified = True
                        break
                    if not email and item.get("verified"):
                        email = item.get("email")
                        email_verified = True

            if not email:
                raise OAuthProviderError("No email address found on GitHub account.")

            if not email_verified:
                raise OAuthEmailUnverifiedError(
                    "Your GitHub email address is not verified. Please verify your email on GitHub."
                )

            return OAuthProfile(
                provider="github",
                provider_account_id=provider_account_id,
                email=email.lower().strip(),
                email_verified=email_verified,
                name=name,
                avatar_url=avatar_url,
                access_token=access_token,
                scopes=scopes,
                raw_metadata=user_data,
            )

    @classmethod
    async def _exchange_google(cls, code: str, redirect_uri: str) -> OAuthProfile:
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
        if not client_id or not client_secret:
            raise OAuthProviderError("Google OAuth credentials are not configured on the server.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Exchange authorization code for token
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            if not token_resp.is_success:
                logger.error("Google token exchange failed: %s", token_resp.text)
                raise OAuthProviderError("Failed to exchange authorization code with Google.")

            token_data = token_resp.json()
            access_token = token_data.get("access_token")

            # 2. Fetch userinfo
            headers = {"Authorization": f"Bearer {access_token}"}
            user_resp = await client.get(GOOGLE_USERINFO_URL, headers=headers)
            if not user_resp.is_success:
                raise OAuthProviderError("Failed to fetch user profile from Google.")

            user_data = user_resp.json()
            provider_account_id = str(user_data["sub"])
            email = user_data.get("email")
            email_verified = bool(user_data.get("email_verified", False))
            name = user_data.get("name")
            avatar_url = user_data.get("picture")

            if not email:
                raise OAuthProviderError("No email address returned from Google.")

            if not email_verified:
                raise OAuthEmailUnverifiedError(
                    "Your Google account email is not verified. Please verify it with Google."
                )

            return OAuthProfile(
                provider="google",
                provider_account_id=provider_account_id,
                email=email.lower().strip(),
                email_verified=email_verified,
                name=name,
                avatar_url=avatar_url,
                access_token=access_token,
                scopes=token_data.get("scope"),
                raw_metadata=user_data,
            )
