import logging
import urllib.parse
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    OAuthAuthorizeUrlResponse,
    OAuthExchangeRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.auth import AuthService
from app.services.auth.exceptions import OAuthStateInvalidError
from app.services.auth.oauth import (
    OAuthClient,
    create_oauth_state,
    verify_oauth_state,
)

logger = logging.getLogger("fussion.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


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
    user, token = await AuthService.register(db, payload)
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
    user, token = await AuthService.authenticate(db, payload)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.get(
    "/oauth/{provider}/url",
    response_model=OAuthAuthorizeUrlResponse,
    summary="Get authorization URL for initiating OAuth handshake",
)
async def get_oauth_url(
    provider: str,
    request: Request,
    redirect_uri: str | None = None,
) -> OAuthAuthorizeUrlResponse:
    target_redirect_uri = redirect_uri or str(request.url_for("oauth_callback", provider=provider))
    state = create_oauth_state(provider)
    auth_url = OAuthClient.get_authorization_url(
        provider=provider,
        redirect_uri=target_redirect_uri,
        state=state,
    )
    return OAuthAuthorizeUrlResponse(
        provider=provider,
        authorization_url=auth_url,
        state=state,
    )


@router.get(
    "/oauth/{provider}/login",
    summary="Redirect user to external OAuth provider (GitHub / Google)",
)
async def oauth_login(
    provider: str,
    request: Request,
    response: Response,
) -> RedirectResponse:
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    state = create_oauth_state(provider)
    auth_url = OAuthClient.get_authorization_url(
        provider=provider,
        redirect_uri=redirect_uri,
        state=state,
    )
    redirect = RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    cookie_kwargs: dict[str, Any] = {
        "key": "fussion_oauth_state",
        "value": state,
        "httponly": True,
        "samesite": "lax",
        "secure": settings.is_production,
        "max_age": settings.OAUTH_STATE_EXPIRE_MINUTES * 60,
        "path": "/",
    }
    if settings.COOKIE_DOMAIN:
        cookie_kwargs["domain"] = settings.COOKIE_DOMAIN
    redirect.set_cookie(**cookie_kwargs)
    return redirect


@router.get(
    "/oauth/{provider}/callback",
    name="oauth_callback",
    summary="Handle OAuth provider redirect, exchange code, link account, and issue session",
)
async def oauth_callback(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
    fussion_oauth_state: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    # 0. Detect if this callback belongs to GitHub App installation flow rather than user login
    if state and code and provider == "github":
        try:
            payload = jwt.decode(
                state,
                settings.effective_jwt_secret_key,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("purpose") == "github_app_oauth_state":
                logger.info(
                    "Detected GitHub App OAuth state in auth callback; forwarding to github oauth callback"
                )
                target_url = (
                    f"{settings.effective_public_api_url}/api/v1/github/oauth/callback"
                    f"?code={urllib.parse.quote(code)}&state={urllib.parse.quote(state)}"
                )
                return RedirectResponse(
                    url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
                )
        except Exception:
            pass

    # 1. Handle provider error redirects (e.g. user denied consent)
    if error:
        err_msg = error_description or error
        target_url = f"{settings.FRONTEND_URL}/login?error={urllib.parse.quote(err_msg)}"
        return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    if not code:
        target_url = f"{settings.FRONTEND_URL}/login?error=missing_code"
        return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # 2. Verify state token and check cookie CSRF match
    verify_oauth_state(state, expected_provider=provider)
    if fussion_oauth_state and state != fussion_oauth_state:
        raise OAuthStateInvalidError("State cookie mismatch; possible CSRF attack.")

    # 3. Exchange code for verified profile
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    profile = await OAuthClient.exchange_code_for_profile(
        provider=provider,
        code=code,
        redirect_uri=redirect_uri,
    )

    # 4. Link or create user and personal organization
    _user, token = await AuthService.link_or_create_oauth_user(db, profile)

    # 5. Clear state cookie and redirect to frontend with session token
    target_url = f"{settings.FRONTEND_URL}/login?oauth_token={urllib.parse.quote(token)}"
    redirect = RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    delete_kwargs: dict[str, Any] = {"key": "fussion_oauth_state", "path": "/"}
    if settings.COOKIE_DOMAIN:
        delete_kwargs["domain"] = settings.COOKIE_DOMAIN
    redirect.delete_cookie(**delete_kwargs)
    return redirect


@router.post(
    "/oauth/exchange",
    response_model=TokenResponse,
    summary="Programmatically exchange an OAuth authorization code for an application token",
)
async def oauth_exchange(
    payload: OAuthExchangeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    verify_oauth_state(payload.state, expected_provider=payload.provider)
    redirect_uri = payload.redirect_uri or str(request.url_for("oauth_callback", provider=payload.provider))
    profile = await OAuthClient.exchange_code_for_profile(
        provider=payload.provider,
        code=payload.code,
        redirect_uri=redirect_uri,
    )
    user, token = await AuthService.link_or_create_oauth_user(db, profile)
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
