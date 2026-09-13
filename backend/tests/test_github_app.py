"""Step E1 — GitHub App install flow, token minting and repository listing.

GitHub's API is mocked with `httpx.MockTransport`; the state signing, browser binding, persistence,
tenancy, OAuth access check and token cache are real.
"""

import uuid
from collections.abc import Callable

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy import select

from app.api.v1.endpoints.github_app import _STATE_COOKIE
from app.core.config import settings
from app.core.database import get_session_factory
from app.core.security import decode_access_token
from app.models.github_installation import GitHubInstallation
from app.services.integration.github_app import (
    GitHubAppError,
    create_install_state,
    create_oauth_state,
    set_github_app_transport,
    verify_install_state,
    verify_oauth_state,
)


def _generate_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


TEST_PRIVATE_KEY = _generate_private_key_pem()
INSTALLATION_ID = 555


class _FakeGitHub:
    def __init__(self) -> None:
        self.requests: list[str] = []
        # What the user's own token can reach; the tests mutate this.
        self.user_installation_ids: list[int] = [INSTALLATION_ID]
        self.token_expires_at = "2030-01-01T00:00:00Z"


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": name,
            "org_name": f"{name}'s Org",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    return token, orgs.json()[0]["id"]


def _user_id_from_token(token: str) -> str:
    return str(decode_access_token(token)["sub"])


async def _record_installation(org_id: str, installation_id: int = INSTALLATION_ID) -> None:
    async with get_session_factory()() as db:
        db.add(
            GitHubInstallation(
                organization_id=uuid.UUID(org_id),
                installation_id=installation_id,
                account_login="acme",
                account_type="Organization",
                repository_selection="selected",
            )
        )
        await db.commit()


def _handler(fake: _FakeGitHub) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        fake.requests.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "ghu_user_token"})
        if path == "/user/installations":
            return httpx.Response(
                200, json={"installations": [{"id": i} for i in fake.user_installation_ids]}
            )
        if path.endswith("/access_tokens"):
            return httpx.Response(
                201, json={"token": "ghs_test_token", "expires_at": fake.token_expires_at}
            )
        if path.startswith("/app/installations/"):
            return httpx.Response(
                200,
                json={
                    "id": INSTALLATION_ID,
                    "account": {"login": "acme", "type": "Organization"},
                    "repository_selection": "selected",
                },
            )
        if path == "/installation/repositories":
            return httpx.Response(
                200,
                json={
                    "total_count": 2,
                    "repositories": [
                        {
                            "full_name": "acme/site",
                            "name": "site",
                            "owner": {"login": "acme"},
                            "private": False,
                            "default_branch": "main",
                        },
                        {
                            "full_name": "acme/docs",
                            "name": "docs",
                            "owner": {"login": "acme"},
                            "private": True,
                            "default_branch": "trunk",
                        },
                    ],
                },
            )
        return httpx.Response(404, json={"message": "not found"})

    return handle


@pytest.fixture
def github_app(monkeypatch: pytest.MonkeyPatch) -> _FakeGitHub:
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "12345")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr(settings, "GITHUB_APP_SLUG", "fussion-test")
    monkeypatch.setattr(settings, "GITHUB_APP_CLIENT_ID", "Iv1.test")
    monkeypatch.setattr(settings, "GITHUB_APP_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000")

    fake = _FakeGitHub()
    set_github_app_transport(httpx.MockTransport(_handler(fake)))
    yield fake
    set_github_app_transport(None)


async def _begin_install(client: AsyncClient, org_id: str, token: str) -> str:
    """Run install-url -> GitHub callback; return the OAuth state from the redirect.

    The client's cookie jar carries the browser nonce, as a real browser would.
    """
    install = await client.get(
        f"/api/v1/organizations/{org_id}/github/install-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert install.status_code == 200
    state = install.json()["url"].split("state=", 1)[1]

    callback = await client.get(
        f"/api/v1/github/callback?state={state}&installation_id={INSTALLATION_ID}"
    )
    assert callback.status_code == 303, callback.text
    location = callback.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize?client_id=Iv1.test&state=")
    return location.split("state=", 1)[1]


@pytest.mark.asyncio
async def test_install_url_requires_a_configured_app(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "GITHUB_APP_ID", None)
    token, org_id = await register_user(client, "gha_unconf@example.com", "GhaUnconf")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/github/install-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_install_url_is_bound_to_a_signed_state(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "gha_install@example.com", "GhaInstall")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/github/install-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    url = resp.json()["url"]
    assert url.startswith("https://github.com/apps/fussion-test/installations/new?state=")

    organization_id, _user_id, nonce = verify_install_state(url.split("state=", 1)[1])
    assert str(organization_id) == org_id
    assert client.cookies.get(_STATE_COOKIE) == nonce


@pytest.mark.asyncio
async def test_full_install_flow_records_the_installation(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "gha_flow@example.com", "GhaFlow")
    oauth_state = await _begin_install(client, org_id, token)

    done = await client.get(
        f"/api/v1/github/oauth/callback?code=test-code&state={oauth_state}"
    )
    assert done.status_code == 303
    assert "github=connected" in done.headers["location"]

    async with get_session_factory()() as db:
        row = (
            await db.execute(
                select(GitHubInstallation).where(
                    GitHubInstallation.installation_id == INSTALLATION_ID
                )
            )
        ).scalar_one()
        assert str(row.organization_id) == org_id
        assert row.account_login == "acme"
        assert row.repository_selection == "selected"


@pytest.mark.asyncio
async def test_install_callback_requires_the_browser_cookie(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    """Login-CSRF: a state minted for another browser must not complete in this one."""
    token, org_id = await register_user(client, "gha_csrf@example.com", "GhaCsrf")
    state = create_install_state(uuid.UUID(org_id), uuid.UUID(_user_id_from_token(token)), "nonce-a")
    # A different browser's cookie.
    client.cookies.set(_STATE_COOKIE, "nonce-b")

    resp = await client.get(
        f"/api/v1/github/callback?state={state}&installation_id={INSTALLATION_ID}"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_refuses_an_installation_the_user_cannot_reach(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    """The hijack case: a valid flow, but the user token does not list the installation."""
    token, org_id = await register_user(client, "gha_hijack@example.com", "GhaHijack")
    github_app.user_installation_ids = [999]  # not INSTALLATION_ID
    oauth_state = await _begin_install(client, org_id, token)

    resp = await client.get(f"/api/v1/github/oauth/callback?code=test-code&state={oauth_state}")
    assert resp.status_code == 403

    async with get_session_factory()() as db:
        rows = (await db.execute(select(GitHubInstallation))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_oauth_callback_never_re_points_another_tenants_installation(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token_a, org_a = await register_user(client, "gha_owner_a@example.com", "GhaOwnerA")
    token_b, org_b = await register_user(client, "gha_owner_b@example.com", "GhaOwnerB")
    await _record_installation(org_a)
    nonce = "nonce-b"
    state = create_oauth_state(
        uuid.UUID(org_b), uuid.UUID(_user_id_from_token(token_b)), INSTALLATION_ID, nonce
    )
    client.cookies.set(_STATE_COOKIE, nonce)

    resp = await client.get(f"/api/v1/github/oauth/callback?code=test-code&state={state}")
    assert resp.status_code == 409

    async with get_session_factory()() as db:
        row = (
            await db.execute(
                select(GitHubInstallation).where(
                    GitHubInstallation.installation_id == INSTALLATION_ID
                )
            )
        ).scalar_one()
    assert str(row.organization_id) == org_a  # unchanged
    del token_a


@pytest.mark.asyncio
async def test_callback_rejects_a_tampered_state(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    resp = await client.get(
        f"/api/v1/github/callback?state=not-a-real-state&installation_id={INSTALLATION_ID}"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_callback_rejects_a_state_for_a_non_member(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    _token_a, org_a = await register_user(client, "gha_org_a@example.com", "GhaOrgA")
    token_b, _org_b = await register_user(client, "gha_user_b@example.com", "GhaUserB")
    nonce = "nonce-b"
    state = create_install_state(
        uuid.UUID(org_a), uuid.UUID(_user_id_from_token(token_b)), nonce
    )
    client.cookies.set(_STATE_COOKIE, nonce)

    resp = await client.get(
        f"/api/v1/github/callback?state={state}&installation_id={INSTALLATION_ID}"
    )
    assert resp.status_code == 404


def test_state_tokens_are_purpose_scoped() -> None:
    org = uuid.uuid4()
    user = uuid.uuid4()
    install_state = create_install_state(org, user, "n")
    oauth_state = create_oauth_state(org, user, INSTALLATION_ID, "n")

    with pytest.raises(GitHubAppError):
        verify_oauth_state(install_state)
    with pytest.raises(GitHubAppError):
        verify_install_state(oauth_state)


@pytest.mark.asyncio
async def test_a_session_token_is_not_a_valid_state(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, _org_id = await register_user(client, "gha_cross@example.com", "GhaCross")
    resp = await client.get(
        f"/api/v1/github/callback?state={token}&installation_id={INSTALLATION_ID}"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_repositories_are_listed_and_tenant_scoped(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "gha_repos@example.com", "GhaRepos")
    other_token, other_org = await register_user(client, "gha_other@example.com", "GhaOther")
    await _record_installation(org_id)

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/github/repositories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 2
    assert {repo["full_name"] for repo in body["repositories"]} == {"acme/site", "acme/docs"}
    assert {repo["default_branch"] for repo in body["repositories"]} == {"main", "trunk"}

    other = await client.get(
        f"/api/v1/organizations/{other_org}/github/repositories",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other.status_code == 200
    assert other.json() == {"total_count": 0, "repositories": [], "page": 1, "per_page": 30}


@pytest.mark.asyncio
async def test_installation_token_is_minted_once_and_cached(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "gha_cache@example.com", "GhaCache")
    await _record_installation(org_id)

    for _ in range(2):
        resp = await client.get(
            f"/api/v1/organizations/{org_id}/github/repositories",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    minted = [request for request in github_app.requests if request.endswith("/access_tokens")]
    assert len(minted) == 1, github_app.requests


@pytest.mark.asyncio
async def test_an_expiring_installation_token_is_re_minted(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "gha_expiry@example.com", "GhaExpiry")
    await _record_installation(org_id)
    # Inside the refresh margin, so the cached token must not be reused.
    github_app.token_expires_at = "2020-01-01T00:00:00Z"

    for _ in range(2):
        resp = await client.get(
            f"/api/v1/organizations/{org_id}/github/repositories",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    minted = [request for request in github_app.requests if request.endswith("/access_tokens")]
    assert len(minted) == 2, github_app.requests


@pytest.mark.asyncio
async def test_installations_are_listed_for_the_tenant(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "gha_list@example.com", "GhaList")
    other_token, other_org = await register_user(client, "gha_list_b@example.com", "GhaListB")
    await _record_installation(org_id)

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/github/installations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["installation_id"] == INSTALLATION_ID

    other = await client.get(
        f"/api/v1/organizations/{other_org}/github/installations",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other.json() == []


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_integration_from_an_installation(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    """E2: an integration created from a selected repo records the installation, not a PAT."""
    token, org_id = await register_user(client, "e2_create@example.com", "E2Create")
    await _record_installation(org_id)
    proj_id = await create_project(client, token, org_id, "E2 Create")

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repository_owner": "acme",
            "repository_name": "site",
            "github_installation_id": INSTALLATION_ID,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["github_installation_id"] == INSTALLATION_ID
    assert body["has_credentials"] is True


@pytest.mark.asyncio
async def test_create_integration_rejects_a_foreign_installation(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    """The installation exists, but it belongs to another organization."""
    token_a, org_a = await register_user(client, "e2_foreign_a@example.com", "E2ForeignA")
    _token_b, org_b = await register_user(client, "e2_foreign_b@example.com", "E2ForeignB")
    await _record_installation(org_b)  # the installation belongs to org B
    proj_a = await create_project(client, token_a, org_a, "E2 Foreign A")

    resp = await client.post(
        f"/api/v1/organizations/{org_a}/projects/{proj_a}/website-integrations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "repository_owner": "acme",
            "repository_name": "site",
            "github_installation_id": INSTALLATION_ID,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_credential_resolver_refuses_when_the_app_is_unconfigured(
    client: AsyncClient, github_app: _FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An App-linked integration cannot authenticate once the app is unconfigured: fail loud."""
    token, org_id = await register_user(client, "e2_unconf@example.com", "E2Unconf")
    await _record_installation(org_id)
    proj_id = await create_project(client, token, org_id, "E2 Unconf")
    created = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repository_owner": "acme",
            "repository_name": "site",
            "github_installation_id": INSTALLATION_ID,
        },
    )
    assert created.status_code == 201

    from app.models.website_integration import WebsiteIntegration
    from app.services.integration.credentials import GitHubCredentialError, resolve_github_token

    monkeypatch.setattr(settings, "GITHUB_APP_ID", None)

    async with get_session_factory()() as db:
        integration = (
            await db.execute(
                select(WebsiteIntegration).where(
                    WebsiteIntegration.project_id == uuid.UUID(proj_id)
                )
            )
        ).scalar_one()
        with pytest.raises(GitHubCredentialError):
            await resolve_github_token(integration)


@pytest.mark.asyncio
async def test_credential_resolver_mints_for_an_app_linked_integration(
    client: AsyncClient, github_app: _FakeGitHub
) -> None:
    token, org_id = await register_user(client, "e2_resolve@example.com", "E2Resolve")
    await _record_installation(org_id)
    proj_id = await create_project(client, token, org_id, "E2 Resolve")
    created = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repository_owner": "acme",
            "repository_name": "site",
            "github_installation_id": INSTALLATION_ID,
        },
    )
    assert created.status_code == 201

    from app.models.website_integration import WebsiteIntegration
    from app.services.integration.credentials import resolve_github_token

    async with get_session_factory()() as db:
        integration = (
            await db.execute(
                select(WebsiteIntegration).where(
                    WebsiteIntegration.project_id == uuid.UUID(proj_id)
                )
            )
        ).scalar_one()
        resolved = await resolve_github_token(integration)

    assert resolved == "ghs_test_token"
    assert any(request.endswith("/access_tokens") for request in github_app.requests)

