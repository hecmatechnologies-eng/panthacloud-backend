"""Step B · B8 — per-origin CORS for the public surface (FR-107, CLAUDE.md §4.11).

The Studio's CORS policy covers the Studio's origin. A customer's site is a different origin per
tenant and a wildcard is forbidden in production, so the public routes carry their own policy: a
preflight is answered only for an origin some integration has registered.

A preflight has no body, so the public key cannot be used to answer it — the check is by origin
alone. The key/origin *pair* is still enforced by the resolver on the real request.
"""

import pytest
from httpx import AsyncClient

from app.llm.gateway import ModelGateway, set_model_gateway
from app.llm.providers.fake import FakeModelProvider
from app.runtime.rate_limit import rate_limiter

CHAT_URL = "/api/v1/public/chat"
STREAM_URL = "/api/v1/public/chat/stream"
ORIGIN = "https://shop.example.com"
UNREGISTERED = "https://evil.example.com"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Rate-limit state is process-global; every test starts from empty (FIRST: Isolated)."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture(autouse=True)
def _model_gateway():
    """A deterministic provider, so these tests never reach a paid API."""
    set_model_gateway(ModelGateway(FakeModelProvider(reply="ok")))
    yield
    set_model_gateway(None)


async def _tenant_with_origin(client: AsyncClient, origin: str = ORIGIN) -> dict:
    """An org/project/integration with one registered origin."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"cors{abs(hash(origin))}@example.com",
            "password": "Password123!",
            "full_name": "Cors",
            "org_name": "Cors Org",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    orgs = await client.get("/api/v1/organizations", headers=headers)
    org_id = orgs.json()[0]["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": "Cors Proj", "slug": "cors-proj"},
    )
    proj_id = project.json()["id"]
    integration = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers=headers,
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    assert integration.status_code == 201
    registered = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/origins",
        headers=headers,
        json={"origin": origin},
    )
    assert registered.status_code == 201
    return integration.json()


def _preflight_headers(origin: str) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }


@pytest.mark.asyncio
async def test_a_preflight_from_a_registered_origin_is_answered(client: AsyncClient) -> None:
    await _tenant_with_origin(client)

    resp = await client.options(CHAT_URL, headers=_preflight_headers(ORIGIN))

    assert resp.status_code == 204
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert "POST" in resp.headers["access-control-allow-methods"]
    assert "content-type" in resp.headers["access-control-allow-headers"].lower()
    assert "origin" in resp.headers.get("vary", "").lower()


@pytest.mark.asyncio
async def test_a_preflight_from_an_unregistered_origin_gets_no_permission(
    client: AsyncClient,
) -> None:
    await _tenant_with_origin(client)

    resp = await client.options(CHAT_URL, headers=_preflight_headers(UNREGISTERED))

    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.asyncio
async def test_a_public_response_echoes_the_registered_origin(client: AsyncClient) -> None:
    integration = await _tenant_with_origin(client)

    resp = await client.post(
        CHAT_URL,
        json={"public_key": integration["public_key"], "message": "hi"},
        headers={"Origin": ORIGIN},
    )

    assert resp.headers.get("access-control-allow-origin") == ORIGIN
    # No cookies on the public surface, so credentials must never be allowed.
    assert "access-control-allow-credentials" not in resp.headers


@pytest.mark.asyncio
async def test_the_middleware_does_not_touch_control_plane_routes(client: AsyncClient) -> None:
    """A customer origin must not acquire CORS rights to the authenticated API."""
    await _tenant_with_origin(client)

    resp = await client.options(
        "/api/v1/organizations", headers=_preflight_headers(ORIGIN)
    )

    assert resp.headers.get("access-control-allow-origin") != ORIGIN


@pytest.mark.asyncio
async def test_a_stream_keeps_its_frames_through_the_middleware(client: AsyncClient) -> None:
    """The middleware wraps responses; the public chat is a stream and must survive intact."""
    integration = await _tenant_with_origin(client)

    resp = await client.post(
        STREAM_URL,
        json={"public_key": integration["public_key"], "message": "hi"},
        headers={"Origin": ORIGIN},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("access-control-allow-origin") == ORIGIN
    assert "event: start" in resp.text
    assert "event: done" in resp.text
