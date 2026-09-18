"""Step B · B1 — each website integration has a public key and registered allowed origins (FR-107).

Nothing enforces either yet; the tenant resolver arrives in B2.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.audit_event import AuditEvent

PUBLIC_KEY_PREFIX = "fussion_pk_"
MAX_ORIGINS = 20


async def register_user(client: AsyncClient, email: str, name: str) -> tuple[str, str, str]:
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
    data = resp.json()
    token = data["access_token"]
    user_id = data["user"]["id"]

    orgs_resp = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    org_id = orgs_resp.json()[0]["id"]
    return token, user_id, org_id


async def create_project(client: AsyncClient, token: str, org_id: str, name: str, slug: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": slug},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def create_integration(client: AsyncClient, token: str, org_id: str, proj_id: str) -> dict:
    resp = await client.post(
        integration_url(org_id, proj_id),
        headers={"Authorization": f"Bearer {token}"},
        json={"repository_owner": "fussion-org", "repository_name": "storefront"},
    )
    assert resp.status_code == 201
    return resp.json()


def integration_url(org_id: str, proj_id: str) -> str:
    return f"/api/v1/organizations/{org_id}/projects/{proj_id}/website-integrations"


def origins_url(org_id: str, proj_id: str) -> str:
    return f"{integration_url(org_id, proj_id)}/origins"


# ============================================================
# 1. ORIGIN NORMALISATION
# ============================================================


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://shop.example.com", "https://shop.example.com"),
        ("HTTPS://Shop.Example.COM:443/", "https://shop.example.com"),
        ("  https://shop.example.com  ", "https://shop.example.com"),
        ("https://shop.example.com:8443", "https://shop.example.com:8443"),
        ("https://bücher.example", "https://xn--bcher-kva.example"),
        # UTS-46, as browsers compute it. The stdlib IDNA2003 codec maps ß to ss, which would
        # both lock out the real faß.example and let an unrelated fass.example match it.
        ("https://faß.example", "https://xn--fa-hia.example"),
        ("https://XN--FA-HIA.example", "https://xn--fa-hia.example"),
        ("https://fass.example", "https://fass.example"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://LOCALHOST:80", "http://localhost"),
        ("http://127.0.0.1:5173", "http://127.0.0.1:5173"),
        ("http://[::1]:8080", "http://[::1]:8080"),
        ("https://[2001:DB8::1]", "https://[2001:db8::1]"),
    ],
)
def test_normalize_origin_accepts(raw: str, expected: str) -> None:
    from app.core.origins import normalize_origin

    assert normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "null",
        "shop.example.com",
        "//shop.example.com",
        "ftp://shop.example.com",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://",
        "https://:443",
        "https://shop.example.com/path",
        "https://shop.example.com/?q=1",
        "https://shop.example.com?q=1",
        "https://shop.example.com#top",
        "https://user:pass@shop.example.com",
        "https://user@shop.example.com",
        "https://*.example.com",
        "https://shop.example.com:0",
        "https://shop.example.com:99999",
        "https://shop.example.com:port",
        "https://shop example.com",
        "https://shop.example.com\\evil",
        "http://shop.example.com",
        "http://localhost.evil.com",
        "https://" + "a" * 250 + ".com",
        # Punycode expansion makes this longer than the column, though the typed text fits.
        "https://" + ("é" * 30 + ".") * 7 + "com",
    ],
)
def test_normalize_origin_rejects(raw: str) -> None:
    from app.core.origins import normalize_origin

    with pytest.raises(ValueError):
        normalize_origin(raw)


# ============================================================
# 2. PUBLIC KEY
# ============================================================


@pytest.mark.asyncio
async def test_public_key_generated_unique_and_immutable(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "pk_owner@example.com", "PkOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_a = await create_project(client, token, org_id, "PK A", "pk-a")
    proj_b = await create_project(client, token, org_id, "PK B", "pk-b")

    key_a = (await create_integration(client, token, org_id, proj_a))["public_key"]
    key_b = (await create_integration(client, token, org_id, proj_b))["public_key"]

    assert key_a.startswith(PUBLIC_KEY_PREFIX)
    assert len(key_a) > len(PUBLIC_KEY_PREFIX) + 30
    assert key_a != key_b

    get_resp = await client.get(integration_url(org_id, proj_a), headers=hdr)
    assert get_resp.json()["public_key"] == key_a

    # The key is server-issued: a client cannot choose or overwrite it.
    patch_resp = await client.patch(
        integration_url(org_id, proj_a),
        headers=hdr,
        json={"public_key": key_b, "default_branch": "release"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["public_key"] == key_a
    assert patch_resp.json()["default_branch"] == "release"

    # Nor on create.
    proj_c = await create_project(client, token, org_id, "PK C", "pk-c")
    create_c = await client.post(
        integration_url(org_id, proj_c),
        headers=hdr,
        json={"repository_owner": "o", "repository_name": "r", "public_key": key_a},
    )
    assert create_c.status_code == 201
    assert create_c.json()["public_key"] not in {key_a, key_b}


# ============================================================
# 3. ORIGIN MANAGEMENT
# ============================================================


@pytest.mark.asyncio
async def test_origin_add_list_delete(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "orig_owner@example.com", "OrigOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Orig Proj", "orig-proj")
    await create_integration(client, token, org_id, proj_id)
    url = origins_url(org_id, proj_id)

    assert (await client.get(url, headers=hdr)).json() == []

    add_resp = await client.post(url, headers=hdr, json={"origin": "HTTPS://Shop.Example.com:443/"})
    assert add_resp.status_code == 201
    added = add_resp.json()
    assert added["origin"] == "https://shop.example.com"
    assert {"id", "origin", "created_at"}.issubset(set(added))

    second = await client.post(url, headers=hdr, json={"origin": "http://localhost:3000"})
    assert second.status_code == 201

    listed = (await client.get(url, headers=hdr)).json()
    assert [o["origin"] for o in listed] == ["https://shop.example.com", "http://localhost:3000"]

    del_resp = await client.delete(f"{url}/{added['id']}", headers=hdr)
    assert del_resp.status_code == 204
    assert [o["origin"] for o in (await client.get(url, headers=hdr)).json()] == ["http://localhost:3000"]

    # Already deleted, and never existed.
    assert (await client.delete(f"{url}/{added['id']}", headers=hdr)).status_code == 404
    assert (await client.delete(f"{url}/{uuid.uuid4()}", headers=hdr)).status_code == 404


@pytest.mark.asyncio
async def test_origin_duplicate_after_normalisation_conflicts(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "dup_owner@example.com", "DupOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Dup Proj", "dup-proj")
    await create_integration(client, token, org_id, proj_id)
    url = origins_url(org_id, proj_id)

    assert (await client.post(url, headers=hdr, json={"origin": "https://shop.example.com"})).status_code == 201
    for variant in ("https://SHOP.example.com", "https://shop.example.com:443", "https://shop.example.com/"):
        resp = await client.post(url, headers=hdr, json={"origin": variant})
        assert resp.status_code == 409, variant

    assert len((await client.get(url, headers=hdr)).json()) == 1


@pytest.mark.asyncio
async def test_origin_invalid_is_rejected(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "inv_owner@example.com", "InvOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Inv Proj", "inv-proj")
    await create_integration(client, token, org_id, proj_id)
    url = origins_url(org_id, proj_id)

    for bad in ("https://shop.example.com/path", "http://shop.example.com", "*", "null", ""):
        resp = await client.post(url, headers=hdr, json={"origin": bad})
        assert resp.status_code == 422, bad

    # The reason reaches the user, not just the status.
    resp = await client.post(url, headers=hdr, json={"origin": "https://shop.example.com/path"})
    messages = [d["msg"] for d in resp.json()["error"]["details"]]
    assert any("without a path" in m for m in messages)

    # Nothing was stored by any of the rejected requests.
    assert (await client.get(url, headers=hdr)).json() == []


@pytest.mark.asyncio
async def test_validation_errors_do_not_echo_the_submitted_value(client: AsyncClient) -> None:
    """B1 added the app's first field_validator, so the 422 body is now rendered in earnest.

    A rejected value must not come back: an over-long github_token would otherwise be echoed.
    """
    token, _, org_id = await register_user(client, "echo_owner@example.com", "EchoOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Echo Proj", "echo-proj")
    await create_integration(client, token, org_id, proj_id)

    secret = "ghp_" + "z" * 600  # Over the 500-character limit, so validation rejects it.
    resp = await client.patch(integration_url(org_id, proj_id), headers=hdr, json={"github_token": secret})
    assert resp.status_code == 422
    assert secret not in resp.text
    assert "zzzz" not in resp.text


@pytest.mark.asyncio
async def test_origin_count_is_capped(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "cap_owner@example.com", "CapOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "Cap Proj", "cap-proj")
    await create_integration(client, token, org_id, proj_id)
    url = origins_url(org_id, proj_id)

    for i in range(MAX_ORIGINS):
        resp = await client.post(url, headers=hdr, json={"origin": f"https://site{i}.example.com"})
        assert resp.status_code == 201

    over = await client.post(url, headers=hdr, json={"origin": "https://one-too-many.example.com"})
    assert over.status_code == 409
    assert len((await client.get(url, headers=hdr)).json()) == MAX_ORIGINS


@pytest.mark.asyncio
async def test_origins_require_an_integration(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "noint_owner@example.com", "NoIntOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "NoInt Proj", "noint-proj")
    url = origins_url(org_id, proj_id)

    assert (await client.get(url, headers=hdr)).status_code == 404
    assert (await client.post(url, headers=hdr, json={"origin": "https://a.example.com"})).status_code == 404


# ============================================================
# 4. TENANT ISOLATION (404, never 403) & RBAC
# ============================================================


@pytest.mark.asyncio
async def test_origins_cross_tenant_access_is_404(client: AsyncClient) -> None:
    token_a, _, org_a = await register_user(client, "oiso_a@example.com", "OIsoA")
    token_b, _, _ = await register_user(client, "oiso_b@example.com", "OIsoB")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}

    proj_a = await create_project(client, token_a, org_a, "OIso A", "oiso-a")
    await create_integration(client, token_a, org_a, proj_a)
    url_a = origins_url(org_a, proj_a)
    origin_a = (await client.post(url_a, headers=hdr_a, json={"origin": "https://a.example.com"})).json()

    assert (await client.get(url_a, headers=hdr_b)).status_code == 404
    assert (await client.post(url_a, headers=hdr_b, json={"origin": "https://b.example.com"})).status_code == 404
    assert (await client.delete(f"{url_a}/{origin_a['id']}", headers=hdr_b)).status_code == 404

    listed = (await client.get(url_a, headers=hdr_a)).json()
    assert [o["origin"] for o in listed] == ["https://a.example.com"]


@pytest.mark.asyncio
async def test_origin_id_from_another_project_is_404(client: AsyncClient) -> None:
    token, _, org_id = await register_user(client, "xproj_owner@example.com", "XProjOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_1 = await create_project(client, token, org_id, "XProj 1", "xproj-1")
    proj_2 = await create_project(client, token, org_id, "XProj 2", "xproj-2")
    await create_integration(client, token, org_id, proj_1)
    await create_integration(client, token, org_id, proj_2)

    origin_1 = (
        await client.post(origins_url(org_id, proj_1), headers=hdr, json={"origin": "https://one.example.com"})
    ).json()

    # Same user, same org, but the origin belongs to project 1's integration.
    resp = await client.delete(f"{origins_url(org_id, proj_2)}/{origin_1['id']}", headers=hdr)
    assert resp.status_code == 404
    assert len((await client.get(origins_url(org_id, proj_1), headers=hdr)).json()) == 1


@pytest.mark.asyncio
async def test_origins_rbac(client: AsyncClient) -> None:
    owner_token, _, org_id = await register_user(client, "orbac_owner@example.com", "ORbacOwner")
    member_token, _, _ = await register_user(client, "orbac_member@example.com", "ORbacMember")
    viewer_token, _, _ = await register_user(client, "orbac_viewer@example.com", "ORbacViewer")
    owner_hdr = {"Authorization": f"Bearer {owner_token}"}
    member_hdr = {"Authorization": f"Bearer {member_token}"}
    viewer_hdr = {"Authorization": f"Bearer {viewer_token}"}

    for email, role in [
        ("orbac_member@example.com", "MEMBER"),
        ("orbac_viewer@example.com", "VIEWER"),
    ]:
        await client.post(
            f"/api/v1/organizations/{org_id}/members",
            headers=owner_hdr,
            json={"email": email, "role": role},
        )

    proj_id = await create_project(client, owner_token, org_id, "ORbac Proj", "orbac-proj")
    await create_integration(client, owner_token, org_id, proj_id)
    url = origins_url(org_id, proj_id)

    existing = (await client.post(url, headers=owner_hdr, json={"origin": "https://owner.example.com"})).json()

    # VIEWER may read, not change.
    assert (await client.get(url, headers=viewer_hdr)).status_code == 200
    assert (await client.post(url, headers=viewer_hdr, json={"origin": "https://v.example.com"})).status_code == 403
    assert (await client.delete(f"{url}/{existing['id']}", headers=viewer_hdr)).status_code == 403

    # MEMBER may change.
    m_add = await client.post(url, headers=member_hdr, json={"origin": "https://m.example.com"})
    assert m_add.status_code == 201
    assert (await client.delete(f"{url}/{m_add.json()['id']}", headers=member_hdr)).status_code == 204


# ============================================================
# 5. CASCADE & AUDIT
# ============================================================


@pytest.mark.asyncio
async def test_origins_deleted_with_integration_and_project(client: AsyncClient) -> None:
    from app.models.allowed_origin import AllowedOrigin

    token, _, org_id = await register_user(client, "ocasc_owner@example.com", "OCascOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_1 = await create_project(client, token, org_id, "OCasc 1", "ocasc-1")
    proj_2 = await create_project(client, token, org_id, "OCasc 2", "ocasc-2")
    await create_integration(client, token, org_id, proj_1)
    await create_integration(client, token, org_id, proj_2)
    await client.post(origins_url(org_id, proj_1), headers=hdr, json={"origin": "https://one.example.com"})
    await client.post(origins_url(org_id, proj_2), headers=hdr, json={"origin": "https://two.example.com"})

    session_factory = get_session_factory()

    async def remaining() -> list[str]:
        async with session_factory() as db:
            return sorted((await db.execute(select(AllowedOrigin.origin))).scalars().all())

    assert await remaining() == ["https://one.example.com", "https://two.example.com"]

    assert (await client.delete(integration_url(org_id, proj_1), headers=hdr)).status_code == 204
    assert await remaining() == ["https://two.example.com"]

    assert (await client.delete(f"/api/v1/organizations/{org_id}/projects/{proj_2}", headers=hdr)).status_code == 204
    assert await remaining() == []


@pytest.mark.asyncio
async def test_origin_changes_are_audited(client: AsyncClient) -> None:
    token, user_id, org_id = await register_user(client, "oaud_owner@example.com", "OAudOwner")
    hdr = {"Authorization": f"Bearer {token}"}
    proj_id = await create_project(client, token, org_id, "OAud Proj", "oaud-proj")
    integration = await create_integration(client, token, org_id, proj_id)
    url = origins_url(org_id, proj_id)

    added = (await client.post(url, headers=hdr, json={"origin": "HTTPS://Audit.Example.com"})).json()
    await client.delete(f"{url}/{added['id']}", headers=hdr)

    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.event_type.in_(["integration.origin.added", "integration.origin.removed"]))
            .order_by(AuditEvent.created_at)
        )
        events = (await db.execute(stmt)).scalars().all()

    assert [e.event_type for e in events] == ["integration.origin.added", "integration.origin.removed"]
    for event in events:
        assert event.payload == {"origin": "https://audit.example.com"}
        assert event.resource_id == uuid.UUID(integration["id"])
        assert event.user_id == uuid.UUID(user_id)
        assert event.organization_id == uuid.UUID(org_id)
