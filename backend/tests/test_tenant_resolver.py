"""Step B · B2 — the runtime tenant resolver (FR-108, FR-107).

Turns an untrusted ``public_key`` and ``Origin`` header into a trusted ``TenantContext``, or
refuses. The security property under test is that every refusal is indistinguishable: an
unknown key, an unregistered origin, and an origin registered to a different integration must
not be tellable apart by response, so no public key or origin can be enumerated.

Nothing calls the resolver yet — B4 is the first public endpoint. These tests exercise it
directly against a real session, as B4 will.
"""

import dataclasses
import uuid

import pytest
from httpx import AsyncClient

from app.core.database import get_session_factory
from app.runtime.resolver import (
    TenantContext,
    TenantResolutionError,
    resolve_tenant,
)

# ============================================================
# Fixtures / helpers (API setup, resolver under test)
# ============================================================


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
    orgs = await client.get(
        "/api/v1/organizations", headers={"Authorization": f"Bearer {token}"}
    )
    return token, orgs.json()[0]["id"]


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_integration(
    client: AsyncClient, token: str, org_id: str, proj_id: str
) -> dict:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    assert resp.status_code == 201
    return resp.json()


async def register_origin(
    client: AsyncClient, token: str, org_id: str, proj_id: str, origin: str
) -> None:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations/origins",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": origin},
    )
    assert resp.status_code == 201


async def resolve(public_key: str | None, origin: str | None) -> TenantContext:
    """Call the resolver on a fresh session, as the runtime endpoint will."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        return await resolve_tenant(db, public_key, origin)


async def assert_refused(public_key: str | None, origin: str | None) -> TenantResolutionError:
    with pytest.raises(TenantResolutionError) as excinfo:
        await resolve(public_key, origin)
    return excinfo.value


async def tenant_fixture(
    client: AsyncClient, email: str, name: str, origin: str
) -> tuple[dict, str, str]:
    """An org/project/integration with one registered origin. Returns integration, org, proj."""
    token, org_id = await register_user(client, email, name)
    proj_id = await create_project(client, token, org_id, f"{name} Proj")
    integration = await create_integration(client, token, org_id, proj_id)
    await register_origin(client, token, org_id, proj_id, origin)
    return integration, org_id, proj_id


# ============================================================
# 1. Successful resolution
# ============================================================


@pytest.mark.asyncio
async def test_resolves_registered_key_and_origin(client: AsyncClient) -> None:
    integration, org_id, proj_id = await tenant_fixture(
        client, "tr_owner@example.com", "TrOwner", "https://shop.example.com"
    )

    ctx = await resolve(integration["public_key"], "https://shop.example.com")

    assert isinstance(ctx, TenantContext)
    assert ctx.organization_id == uuid.UUID(org_id)
    assert ctx.project_id == uuid.UUID(proj_id)
    assert ctx.integration_id == uuid.UUID(integration["id"])
    assert ctx.origin == "https://shop.example.com"


@pytest.mark.asyncio
async def test_incoming_origin_is_normalised_before_matching(client: AsyncClient) -> None:
    integration, _, _ = await tenant_fixture(
        client, "tr_norm@example.com", "TrNorm", "https://shop.example.com"
    )

    # The same origin as a browser or a sloppy client might spell it.
    ctx = await resolve(integration["public_key"], "HTTPS://Shop.Example.COM:443/")
    assert ctx.origin == "https://shop.example.com"


@pytest.mark.asyncio
async def test_context_is_immutable(client: AsyncClient) -> None:
    integration, _, _ = await tenant_fixture(
        client, "tr_frozen@example.com", "TrFrozen", "https://shop.example.com"
    )
    ctx = await resolve(integration["public_key"], "https://shop.example.com")

    # A later stage must not be able to widen tenancy by mutating the carrier.
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.organization_id = uuid.uuid4()  # type: ignore[misc]


# ============================================================
# 2. Refusals — unknown key, unregistered origin, malformed input
# ============================================================


@pytest.mark.asyncio
async def test_unknown_key_is_refused(client: AsyncClient) -> None:
    await tenant_fixture(
        client, "tr_unknown@example.com", "TrUnknown", "https://shop.example.com"
    )
    await assert_refused("fussion_pk_" + "x" * 32, "https://shop.example.com")


@pytest.mark.asyncio
async def test_unregistered_origin_is_refused(client: AsyncClient) -> None:
    integration, _, _ = await tenant_fixture(
        client, "tr_unreg@example.com", "TrUnreg", "https://shop.example.com"
    )
    await assert_refused(integration["public_key"], "https://evil.example.com")


@pytest.mark.asyncio
async def test_origin_registered_to_another_integration_is_refused(
    client: AsyncClient,
) -> None:
    integration_a, _, _ = await tenant_fixture(
        client, "tr_a@example.com", "TrA", "https://a.example.com"
    )
    integration_b, _, _ = await tenant_fixture(
        client, "tr_b@example.com", "TrB", "https://b.example.com"
    )

    # Each key only ever resolves its own origin, in both directions.
    await assert_refused(integration_a["public_key"], "https://b.example.com")
    await assert_refused(integration_b["public_key"], "https://a.example.com")


@pytest.mark.asyncio
async def test_cross_tenant_combination_is_refused_and_correct_pair_resolves(
    client: AsyncClient,
) -> None:
    integration_a, org_a, _ = await tenant_fixture(
        client, "tr_iso_a@example.com", "TrIsoA", "https://a.example.com"
    )
    integration_b, org_b, _ = await tenant_fixture(
        client, "tr_iso_b@example.com", "TrIsoB", "https://b.example.com"
    )

    await assert_refused(integration_a["public_key"], "https://b.example.com")

    ctx_a = await resolve(integration_a["public_key"], "https://a.example.com")
    ctx_b = await resolve(integration_b["public_key"], "https://b.example.com")
    assert ctx_a.organization_id == uuid.UUID(org_a)
    assert ctx_b.organization_id == uuid.UUID(org_b)
    assert ctx_a.organization_id != ctx_b.organization_id


@pytest.mark.asyncio
async def test_all_refusal_causes_are_indistinguishable(client: AsyncClient) -> None:
    integration_a, _, _ = await tenant_fixture(
        client, "tr_same_a@example.com", "TrSameA", "https://a.example.com"
    )
    integration_b, _, _ = await tenant_fixture(
        client, "tr_same_b@example.com", "TrSameB", "https://b.example.com"
    )

    # The three causes the slice names: unknown key, unregistered origin, and an origin
    # registered to a different integration. None may be tellable from another.
    refusals = [
        await assert_refused("fussion_pk_" + "y" * 32, "https://a.example.com"),
        await assert_refused(integration_a["public_key"], "https://evil.example.com"),
        await assert_refused(integration_a["public_key"], "https://b.example.com"),
        await assert_refused(integration_b["public_key"], "https://a.example.com"),
    ]

    assert all(type(r) is TenantResolutionError for r in refusals)
    assert len({str(r) for r in refusals}) == 1


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "   ",
        "null",
        "https://shop.example.com/path",
        "http://shop.example.com",
        "javascript:alert(1)",
        "not a url",
    ],
)
@pytest.mark.asyncio
async def test_missing_or_malformed_origin_is_refused(
    client: AsyncClient, origin: str | None
) -> None:
    integration, _, _ = await tenant_fixture(
        client, "tr_bad_origin@example.com", "TrBadOrigin", "https://shop.example.com"
    )
    await assert_refused(integration["public_key"], origin)


@pytest.mark.parametrize("public_key", [None, "", "   ", "not-a-key"])
@pytest.mark.asyncio
async def test_missing_or_malformed_key_is_refused(
    client: AsyncClient, public_key: str | None
) -> None:
    await tenant_fixture(
        client, "tr_bad_key@example.com", "TrBadKey", "https://shop.example.com"
    )
    await assert_refused(public_key, "https://shop.example.com")
