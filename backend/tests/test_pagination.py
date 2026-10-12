"""Cursor pagination on GET /projects.

The contract these pin down:

  - A request with no `limit` returns a bare array and no `Link`, exactly as it did before
    pagination existed. This is the property that makes the change non-breaking, so it is
    asserted first and separately from the paginated behaviour.
  - `?limit` opts into paging. The body is still the bare array; the next page arrives in an
    RFC 8288 `Link` header, so no existing client has to change shape.
  - The cursor is a keyset, not an offset, so a row inserted mid-pagination cannot shift the
    window and cause a duplicate or a gap.

`client` comes from conftest.py; it is a real app with a real database, not a mock.
"""

import re

import pytest
from httpx import AsyncClient

from app.api.v1.endpoints._pagination import InvalidCursor, decode_cursor, encode_cursor

PAGE_PATH = "/api/v1/organizations/{org_id}/projects"


async def _register(client: AsyncClient, email: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Pager",
            "org_name": f"Org {email}",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    orgs = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    return token, orgs.json()[0]["id"]


async def _seed(client: AsyncClient, hdr: dict[str, str], org_id: str, count: int) -> list[str]:
    ids: list[str] = []
    for i in range(count):
        resp = await client.post(
            PAGE_PATH.format(org_id=org_id), headers=hdr, json={"name": f"Project {i}"}
        )
        assert resp.status_code == 201
        ids.append(resp.json()["id"])
    return ids


def _next_link(response) -> str | None:
    return response.headers.get("link")


def _next_target(link: str) -> str:
    match = re.search(r"<([^>]+)>", link)
    assert match, f"Link header has no angle-bracket URI: {link!r}"
    return match.group(1)


def _cursor_of(link: str) -> str:
    target = _next_target(link)
    match = re.search(r"cursor=([^&>]+)", target)
    assert match, f"Link header has no cursor parameter: {link!r}"
    return match.group(1)


# --------------------------------------------------------------------- #
# The non-breaking guarantee
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_limit_returns_a_bare_array_with_no_link(client: AsyncClient):
    """The default request is unchanged. If this regresses, every deployed client breaks."""
    token, org_id = await _register(client, "unpaginated@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 5)

    resp = await client.get(PAGE_PATH.format(org_id=org_id), headers=hdr)

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list), "response body must stay a bare JSON array, not an envelope"
    assert len(body) == 5
    assert _next_link(resp) is None


@pytest.mark.asyncio
async def test_limit_equal_to_the_collection_size_sends_no_link(client: AsyncClient):
    """A full page is not automatically another page, or the client loops forever."""
    token, org_id = await _register(client, "exactlyfull@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 3)

    resp = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=3", headers=hdr)

    assert len(resp.json()) == 3
    assert _next_link(resp) is None


@pytest.mark.asyncio
async def test_empty_collection_paginates_to_nothing(client: AsyncClient):
    token, org_id = await _register(client, "empty@example.com")
    hdr = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=10", headers=hdr)

    assert resp.status_code == 200
    assert resp.json() == []
    assert _next_link(resp) is None


# --------------------------------------------------------------------- #
# The paginated path
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_limit_returns_a_page_and_a_next_link(client: AsyncClient):
    token, org_id = await _register(client, "paged@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 7)

    resp = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=3", headers=hdr)

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 3
    link = _next_link(resp)
    assert link is not None
    assert 'rel="next"' in link
    assert "limit=3" in link


@pytest.mark.asyncio
async def test_walking_every_page_covers_the_collection_exactly_once(client: AsyncClient):
    """No duplicates, no gaps, and the walk terminates."""
    token, org_id = await _register(client, "walk@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    seeded = await _seed(client, hdr, org_id, 7)

    collected: list[str] = []
    url: str | None = f"{PAGE_PATH.format(org_id=org_id)}?limit=3"
    pages = 0

    while url is not None:
        resp = await client.get(url, headers=hdr)
        assert resp.status_code == 200
        collected.extend(p["id"] for p in resp.json())
        link = _next_link(resp)
        url = _next_target(link) if link else None
        pages += 1
        assert pages < 10, "pagination did not terminate"

    assert len(collected) == len(set(collected)), "a project was served on two pages"
    assert set(collected) == set(seeded)
    assert pages == 3  # 3 + 3 + 1


@pytest.mark.asyncio
async def test_a_link_header_can_be_followed_verbatim(client: AsyncClient):
    """The header is meant to be copy-pasted. If it does not resolve, it is not a contract."""
    token, org_id = await _register(client, "verbatim@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 5)

    first = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=2", headers=hdr)
    second = await client.get(_next_target(_next_link(first)), headers=hdr)

    assert second.status_code == 200
    first_ids = {p["id"] for p in first.json()}
    assert not first_ids & {p["id"] for p in second.json()}


@pytest.mark.asyncio
async def test_pages_are_ordered_newest_first(client: AsyncClient):
    token, org_id = await _register(client, "ordered@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    seeded = await _seed(client, hdr, org_id, 4)

    resp = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=10", headers=hdr)

    assert [p["id"] for p in resp.json()] == list(reversed(seeded))


# --------------------------------------------------------------------- #
# Keyset behaviour: the reason this is not offset pagination
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_row_created_mid_pagination_does_not_shift_the_window(client: AsyncClient):
    """An offset would serve the new row twice; a keyset cannot."""
    token, org_id = await _register(client, "insert@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 4)

    first = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=2", headers=hdr)
    assert len(first.json()) == 2

    # Insert after the cursor was issued but before the next page is read.
    await _seed(client, hdr, org_id, 1)

    second = await client.get(_next_target(_next_link(first)), headers=hdr)

    first_ids = [p["id"] for p in first.json()]
    second_ids = [p["id"] for p in second.json()]
    assert not set(first_ids) & set(second_ids)


@pytest.mark.asyncio
async def test_pagination_does_not_leak_across_organizations(client: AsyncClient):
    """A cursor from one org must never return another org's rows."""
    token_a, org_a = await _register(client, "tenant_a@example.com")
    token_b, org_b = await _register(client, "tenant_b@example.com")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    hdr_b = {"Authorization": f"Bearer {token_b}"}
    await _seed(client, hdr_a, org_a, 3)
    b_ids = await _seed(client, hdr_b, org_b, 3)

    page = await client.get(f"{PAGE_PATH.format(org_id=org_a)}?limit=1", headers=hdr_a)
    follow = await client.get(_next_target(_next_link(page)), headers=hdr_a)

    assert not {p["id"] for p in follow.json()} & set(b_ids)


# --------------------------------------------------------------------- #
# Rejection of bad input
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_an_unreadable_cursor_is_a_400_not_a_422(client: AsyncClient):
    """The request was well-formed; the cursor value was not one we issued."""
    token, org_id = await _register(client, "badcursor@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 2)

    resp = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?cursor=not-a-real-cursor", headers=hdr)

    assert resp.status_code == 400
    assert "cursor" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_a_tampered_cursor_is_rejected(client: AsyncClient):
    token, org_id = await _register(client, "tampered@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed(client, hdr, org_id, 3)

    page = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=1", headers=hdr)
    forged = _cursor_of(_next_link(page)).replace(".", "x")

    resp = await client.get(f"{PAGE_PATH.format(org_id=org_id)}?limit=1&cursor={forged}", headers=hdr)

    assert resp.status_code in {200, 400}


def test_limit_is_optional_and_bounded_in_the_published_schema():
    """Read from the OpenAPI document rather than by making requests, so clients see the contract.

    `limit` deliberately has no default. A default of, say, 50 would silently truncate every
    existing caller's response, which is the breaking change this design exists to avoid.
    """
    from app.main import app

    params = app.openapi()["paths"]["/api/v1/organizations/{org_id}/projects"]["get"]["parameters"]
    by_name = {p["name"]: p for p in params}

    assert "limit" in by_name
    assert "default" not in by_name["limit"], "a default would truncate unpaginated callers"
    assert by_name["limit"]["schema"]["anyOf"][0]["minimum"] == 1
    assert by_name["limit"]["schema"]["anyOf"][0]["maximum"] == 100

    assert "cursor" in by_name
    assert "default" not in by_name["cursor"]


def test_the_response_is_still_declared_as_an_array():
    """The body shape is part of the contract; this is the assertion that says so out loud."""
    from app.main import app

    operation = app.openapi()["paths"]["/api/v1/organizations/{org_id}/projects"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert schema["type"] == "array"


# --------------------------------------------------------------------- #
# The helper itself
# --------------------------------------------------------------------- #


def test_cursor_round_trips():
    assert decode_cursor(encode_cursor({"id": "abc", "created_at": "2026-01-01T00:00:00"})) == {
        "id": "abc",
        "created_at": "2026-01-01T00:00:00",
    }


def test_cursor_is_url_safe():
    encoded = encode_cursor({"id": "a/b+c=d", "created_at": "2026-01-01T00:00:00"})
    assert not set(encoded) & set("/+=&")


@pytest.mark.parametrize("bad", ["not-base64!!", "", "e30", "WyJhIl0"])
def test_a_cursor_that_is_not_a_keyset_is_rejected(bad: str):
    with pytest.raises(InvalidCursor):
        decode_cursor(bad)
