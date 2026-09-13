"""GitHub App installation flow (step E1).

The platform holds no user credential. A GitHub App authenticates as itself: it signs a short JWT
with the app private key, exchanges it for a **short-lived installation access token**, and caches
that token until shortly before it expires.

The install flow has two steps, because an installation id alone proves nothing about who sent it
(GitHub installation ids are enumerable). After GitHub's install redirect, the user is sent through
GitHub's user authorization (OAuth), and the returned user-to-server token is used to confirm the
user can actually reach that installation before it is recorded. The tenant is carried in a signed
`state` at each step, so a callback cannot be pointed at the wrong organization.

This module is the seam the credential resolver will use; the model never sees a token
(`CLAUDE.md` §4.2).
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
import jwt

from app.core.config import settings

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_ACCEPT = "application/vnd.github+json"
_GITHUB_API_VERSION = "2022-11-28"
# The app JWT is valid for at most 10 minutes on GitHub's side; sign for 9 and backdate 60s for
# clock skew.
_APP_JWT_TTL_SECONDS = 540
_APP_JWT_BACKDATE_SECONDS = 60
# Reuse an installation token until this many seconds before it expires.
_TOKEN_REFRESH_MARGIN_SECONDS = 60
_PURPOSE_INSTALL = "github_app_install_state"
_PURPOSE_OAUTH = "github_app_oauth_state"
# Bound the user-installation scan; past this we refuse loudly rather than answer wrongly.
_MAX_USER_INSTALLATION_PAGES = 100
_USER_INSTALLATION_PAGE_SIZE = 100


class GitHubAppNotConfiguredError(Exception):
    """No GitHub App is configured; the install flow is unavailable (fail loud)."""


class GitHubAppError(Exception):
    """A GitHub App API call failed. Carries the upstream status where there is one."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def is_configured() -> bool:
    return bool(
        settings.GITHUB_APP_ID
        and settings.GITHUB_APP_PRIVATE_KEY
        and settings.GITHUB_APP_SLUG
        and settings.GITHUB_APP_CLIENT_ID
        and settings.GITHUB_APP_CLIENT_SECRET
    )


def _require_configured() -> None:
    if not is_configured():
        raise GitHubAppNotConfiguredError(
            "No GitHub App is configured. Set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, "
            "GITHUB_APP_SLUG, GITHUB_APP_CLIENT_ID and GITHUB_APP_CLIENT_SECRET."
        )


def _private_key() -> str:
    # A PEM pasted into an environment variable usually carries literal "\n"; accept both.
    return (settings.GITHUB_APP_PRIVATE_KEY or "").replace("\\n", "\n")


def _sign_state(purpose: str, claims: dict[str, object]) -> str:
    now = datetime.now(UTC)
    payload = {
        "purpose": purpose,
        **claims,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.GITHUB_APP_STATE_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, settings.effective_jwt_secret_key, algorithm=settings.JWT_ALGORITHM)


def _decode_state(state: str, purpose: str) -> dict[str, object]:
    try:
        payload = jwt.decode(
            state, settings.effective_jwt_secret_key, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise GitHubAppError("The install state is invalid or has expired.", 400) from exc
    if payload.get("purpose") != purpose:
        raise GitHubAppError("The state is not valid for this step.", 400)
    return payload


def create_install_state(organization_id: uuid.UUID, user_id: uuid.UUID, nonce: str) -> str:
    """Bind the install entry point to the org, user and browser that started it.

    The nonce is also set as a cookie on the initiating browser; both callbacks require the state's
    nonce and the cookie to match, so a link crafted by one user cannot be completed by another
    (login CSRF / consent phishing).
    """
    return _sign_state(
        _PURPOSE_INSTALL, {"org": str(organization_id), "user": str(user_id), "nonce": nonce}
    )


def verify_install_state(state: str) -> tuple[uuid.UUID, uuid.UUID, str]:
    payload = _decode_state(state, _PURPOSE_INSTALL)
    try:
        return uuid.UUID(str(payload["org"])), uuid.UUID(str(payload["user"])), str(payload["nonce"])
    except (KeyError, ValueError) as exc:
        raise GitHubAppError("The install state is malformed.", 400) from exc


def create_oauth_state(
    organization_id: uuid.UUID, user_id: uuid.UUID, installation_id: int, nonce: str
) -> str:
    """Bind the OAuth step to the org, user, installation and initiating browser."""
    return _sign_state(
        _PURPOSE_OAUTH,
        {
            "org": str(organization_id),
            "user": str(user_id),
            "installation": installation_id,
            "nonce": nonce,
        },
    )


def verify_oauth_state(state: str) -> tuple[uuid.UUID, uuid.UUID, int, str]:
    payload = _decode_state(state, _PURPOSE_OAUTH)
    try:
        return (
            uuid.UUID(str(payload["org"])),
            uuid.UUID(str(payload["user"])),
            int(payload["installation"]),  # type: ignore[arg-type]
            str(payload["nonce"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise GitHubAppError("The OAuth state is malformed.", 400) from exc


def build_install_url(state: str) -> str:
    _require_configured()
    return (
        f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new"
        f"?state={quote(state)}"
    )


def build_oauth_authorize_url(state: str) -> str:
    _require_configured()
    return (
        f"{GITHUB_OAUTH_AUTHORIZE_URL}?client_id={quote(settings.GITHUB_APP_CLIENT_ID or '')}"
        f"&state={quote(state)}"
    )


def build_app_jwt() -> str:
    _require_configured()
    now = int(time.time())
    payload = {
        "iat": now - _APP_JWT_BACKDATE_SECONDS,
        "exp": now + _APP_JWT_TTL_SECONDS,
        "iss": settings.GITHUB_APP_ID,
    }
    return jwt.encode(payload, _private_key(), algorithm="RS256")


@dataclass
class _CachedToken:
    token: str
    expires_at: float


_token_cache: dict[int, _CachedToken] = {}
_token_lock = asyncio.Lock()
_transport: httpx.AsyncBaseTransport | None = None


def set_github_app_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Install a transport for tests; None restores the real network."""
    global _transport
    _transport = transport
    _token_cache.clear()


def _app_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {build_app_jwt()}",
        "Accept": _GITHUB_ACCEPT,
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }


def _installation_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": _GITHUB_ACCEPT,
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }


async def _request(
    method: str, url: str, *, headers: dict[str, str], params: dict[str, str] | None = None
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(transport=_transport) as client:
            return await client.request(method, url, headers=headers, params=params, timeout=15.0)
    except httpx.HTTPError as exc:
        # A transport failure is a GitHub failure, not an unexpected one: callers map it to a 502.
        raise GitHubAppError("Could not reach GitHub.", 502) from exc


async def exchange_oauth_code(code: str) -> str:
    """Exchange a user-authorization code for a user-to-server token."""
    _require_configured()
    try:
        async with httpx.AsyncClient(transport=_transport) as client:
            resp = await client.post(
                GITHUB_OAUTH_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_APP_CLIENT_ID,
                    "client_secret": settings.GITHUB_APP_CLIENT_SECRET,
                    "code": code,
                },
                timeout=15.0,
            )
    except httpx.HTTPError as exc:
        raise GitHubAppError("Could not reach GitHub.", 502) from exc
    if resp.status_code != 200:
        raise GitHubAppError("GitHub rejected the authorization code.", 400)
    token = resp.json().get("access_token")
    if not token:
        raise GitHubAppError("GitHub returned no user token.", 400)
    return str(token)


async def user_can_access_installation(user_token: str, installation_id: int) -> bool:
    """Whether the authenticated user's installations include `installation_id`.

    This is the control that makes the install callback safe: an installation id alone proves
    nothing, so the user must prove access to it through their own GitHub token.
    """
    for page in range(1, _MAX_USER_INSTALLATION_PAGES + 1):
        resp = await _request(
            "GET",
            f"{GITHUB_API_BASE}/user/installations",
            headers={
                "Authorization": f"Bearer {user_token}",
                "Accept": _GITHUB_ACCEPT,
                "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            },
            params={"page": str(page), "per_page": str(_USER_INSTALLATION_PAGE_SIZE)},
        )
        if resp.status_code != 200:
            raise GitHubAppError("Could not read the user's installations.", resp.status_code)
        installations = resp.json().get("installations", [])
        if any(int(item.get("id", -1)) == installation_id for item in installations):
            return True
        if len(installations) < _USER_INSTALLATION_PAGE_SIZE:
            return False
    raise GitHubAppError(
        "The GitHub account has too many installations to verify in one request.", 400
    )


async def mint_installation_token(installation_id: int) -> str:
    """A valid installation access token, minted if the cached one is near expiry."""
    _require_configured()
    async with _token_lock:
        cached = _token_cache.get(installation_id)
        if cached and cached.expires_at - _TOKEN_REFRESH_MARGIN_SECONDS > time.time():
            return cached.token

        resp = await _request(
            "POST",
            f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
            headers=_app_headers(),
        )
        if resp.status_code != 201:
            raise GitHubAppError(
                f"Could not mint an installation token: {resp.text}", resp.status_code
            )
        data = resp.json()
        token = data.get("token")
        expires_at_raw = data.get("expires_at")
        if not token or not expires_at_raw:
            raise GitHubAppError("GitHub returned an unreadable installation token.", 502)
        expires_at = datetime.fromisoformat(expires_at_raw).timestamp()
        _token_cache[installation_id] = _CachedToken(token=token, expires_at=expires_at)
        return token


async def get_installation(installation_id: int) -> dict[str, object]:
    """The installation's metadata, as GitHub reports it (account, repository selection)."""
    _require_configured()
    resp = await _request(
        "GET", f"{GITHUB_API_BASE}/app/installations/{installation_id}", headers=_app_headers()
    )
    if resp.status_code != 200:
        raise GitHubAppError(f"Could not read the installation: {resp.text}", resp.status_code)
    return resp.json()


async def list_installation_repositories(
    installation_id: int, *, page: int = 1, per_page: int = 30
) -> dict[str, object]:
    """The repositories the installation can reach, one page at a time."""
    token = await mint_installation_token(installation_id)
    resp = await _request(
        "GET",
        f"{GITHUB_API_BASE}/installation/repositories",
        headers=_installation_headers(token),
        params={"page": str(page), "per_page": str(per_page)},
    )
    if resp.status_code != 200:
        raise GitHubAppError(f"Could not list repositories: {resp.text}", resp.status_code)
    data = resp.json()
    return {
        "total_count": data.get("total_count", 0),
        "repositories": [
            {
                "full_name": repo.get("full_name"),
                "name": repo.get("name"),
                "owner": (repo.get("owner") or {}).get("login"),
                "private": repo.get("private", False),
                "default_branch": repo.get("default_branch", "main"),
            }
            for repo in data.get("repositories", [])
        ],
        "page": page,
        "per_page": per_page,
    }
