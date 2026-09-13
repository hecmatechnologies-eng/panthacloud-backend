"""GitHub App connection endpoints (step E1).

Two-step install, because an installation id alone proves nothing:

1. ``/github/callback`` — GitHub's install redirect. Verifies the signed state and the browser
   cookie set at ``/install-url`` (login-CSRF defence), re-checks membership, then sends the user
   through GitHub user authorization (OAuth).
2. ``/github/oauth/callback`` — verifies state and cookie, exchanges the code for a user-to-server
   token, and confirms the user can actually reach the installation before recording it.

No credential is stored or returned. A missing app configuration fails loud (503) rather than
offering a button that cannot work.
"""

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import Permission, has_permission
from app.models.github_installation import GitHubInstallation
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.github_app import (
    GitHubInstallationRead,
    GitHubInstallUrlRead,
    GitHubRepositoryList,
    GitHubRepositoryRead,
)
from app.services.integration.github_app import (
    GitHubAppError,
    GitHubAppNotConfiguredError,
    build_install_url,
    build_oauth_authorize_url,
    create_install_state,
    create_oauth_state,
    exchange_oauth_code,
    get_installation,
    list_installation_repositories,
    user_can_access_installation,
    verify_install_state,
    verify_oauth_state,
)

router = APIRouter(tags=["GitHub App"])

_Tenant = Annotated[
    tuple[Organization, Membership], Depends(require_permission(Permission.INTEGRATION_CREATE))
]
# The nonce cookie that binds an install flow to the browser that started it.
_STATE_COOKIE = "fussion_github_state"


def _set_state_cookie(response: Response, nonce: str) -> None:
    response.set_cookie(
        _STATE_COOKIE,
        nonce,
        max_age=settings.GITHUB_APP_STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )


def _nonce_matches(cookie_nonce: str | None, state_nonce: str) -> None:
    if not cookie_nonce or not secrets.compare_digest(cookie_nonce, state_nonce):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This install link did not originate in this browser. Start the connection again.",
        )


async def _authorize_state_user(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Re-check that the state's user is still a member who may connect an installation."""
    membership = (
        await db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None or not has_permission(membership.role, Permission.INTEGRATION_CREATE):
        # Same 404 as a missing organization: never reveal which orgs exist.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found."
        )


@router.get(
    "/organizations/{org_id}/github/install-url",
    response_model=GitHubInstallUrlRead,
    summary="URL to install the GitHub App for this organization",
)
async def github_install_url(
    org_id: uuid.UUID,
    tenant: _Tenant,
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> GitHubInstallUrlRead:
    del org_id
    organization, _ = tenant
    try:
        nonce = secrets.token_urlsafe(32)
        state = create_install_state(organization.id, user.id, nonce)
        _set_state_cookie(response, nonce)
        return GitHubInstallUrlRead(url=build_install_url(state))
    except GitHubAppNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None


@router.get("/github/callback", include_in_schema=False)
async def github_install_callback(
    state: Annotated[str, Query()],
    installation_id: Annotated[int, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    state_cookie: Annotated[str | None, Cookie(alias=_STATE_COOKIE)] = None,
) -> RedirectResponse:
    """GitHub's post-install redirect: verify the state, then begin user authorization."""
    try:
        organization_id, user_id, nonce = verify_install_state(state)
    except GitHubAppError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    _nonce_matches(state_cookie, nonce)

    await _authorize_state_user(db, organization_id, user_id)

    try:
        oauth_state = create_oauth_state(organization_id, user_id, installation_id, nonce)
        redirect = RedirectResponse(
            build_oauth_authorize_url(oauth_state), status_code=status.HTTP_303_SEE_OTHER
        )
        _set_state_cookie(redirect, nonce)
        return redirect
    except GitHubAppNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None


@router.get("/github/oauth/callback", include_in_schema=False)
async def github_oauth_callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    state_cookie: Annotated[str | None, Cookie(alias=_STATE_COOKIE)] = None,
) -> RedirectResponse:
    """User authorization: confirm the user can reach the installation, then record it."""
    try:
        organization_id, user_id, installation_id, nonce = verify_oauth_state(state)
    except GitHubAppError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    _nonce_matches(state_cookie, nonce)

    await _authorize_state_user(db, organization_id, user_id)

    try:
        user_token = await exchange_oauth_code(code)
        allowed = await user_can_access_installation(user_token, installation_id)
    except GitHubAppNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    except GitHubAppError as exc:
        # A bad/expired code is the client's to fix (400); anything else is upstream (502).
        if exc.status_code is not None and 400 <= exc.status_code < 500:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub could not verify the installation.",
        ) from exc

    # One refusal for "no such installation" and "not yours": the user token decides, so the
    # endpoint is not an oracle for enumerating installation ids.
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This GitHub account cannot access that installation.",
        )

    try:
        installation = await get_installation(installation_id)
    except GitHubAppNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    except GitHubAppError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The installation could not be read from GitHub.",
        ) from exc

    account = installation.get("account") or {}
    existing = (
        await db.execute(
            select(GitHubInstallation).where(
                GitHubInstallation.installation_id == installation_id
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.organization_id != organization_id:
        # Never re-point an installation another tenant already recorded.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That installation is already connected to another organization.",
        )

    if existing is None:
        db.add(
            GitHubInstallation(
                organization_id=organization_id,
                installation_id=installation_id,
                account_login=str(account.get("login") or ""),
                account_type=str(account.get("type") or "User"),
                repository_selection=str(installation.get("repository_selection") or "selected"),
            )
        )
    else:
        existing.account_login = str(account.get("login") or existing.account_login)
        existing.account_type = str(account.get("type") or existing.account_type)
        existing.repository_selection = str(
            installation.get("repository_selection") or existing.repository_selection
        )

    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent callbacks raced the insert; the unique index kept one owner.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That installation is already connected to another organization.",
        ) from None

    redirect = RedirectResponse(
        f"{settings.FRONTEND_URL}/studio?github=connected", status_code=status.HTTP_303_SEE_OTHER
    )
    redirect.delete_cookie(_STATE_COOKIE, path="/")
    return redirect


@router.get(
    "/organizations/{org_id}/github/installations",
    response_model=list[GitHubInstallationRead],
    summary="List this organization's GitHub App installations",
)
async def github_installations(
    org_id: uuid.UUID,
    tenant: _Tenant,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GitHubInstallationRead]:
    del org_id
    organization, _ = tenant
    rows = (
        await db.execute(
            select(GitHubInstallation)
            .where(GitHubInstallation.organization_id == organization.id)
            .order_by(GitHubInstallation.created_at.asc())
        )
    ).scalars().all()
    return [GitHubInstallationRead.model_validate(row) for row in rows]


@router.get(
    "/organizations/{org_id}/github/repositories",
    response_model=GitHubRepositoryList,
    summary="List repositories the organization's installation can reach",
)
async def github_repositories(
    org_id: uuid.UUID,
    tenant: _Tenant,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
) -> GitHubRepositoryList:
    del org_id
    organization, _ = tenant
    installations = (
        await db.execute(
            select(GitHubInstallation)
            .where(GitHubInstallation.organization_id == organization.id)
            .order_by(GitHubInstallation.created_at.asc())
        )
    ).scalars().all()

    if not installations:
        return GitHubRepositoryList(
            total_count=0, repositories=[], page=page, per_page=per_page
        )

    total = 0
    repositories: list[GitHubRepositoryRead] = []
    try:
        for installation in installations:
            result = await list_installation_repositories(
                installation.installation_id, page=page, per_page=per_page
            )
            total += int(result["total_count"])
            repositories.extend(
                GitHubRepositoryRead.model_validate(repo) for repo in result["repositories"]
            )
    except GitHubAppNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    except GitHubAppError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The repositories could not be listed from GitHub.",
        ) from None

    return GitHubRepositoryList(
        total_count=total, repositories=repositories, page=page, per_page=per_page
    )
