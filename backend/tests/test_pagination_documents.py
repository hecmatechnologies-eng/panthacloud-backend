"""Cursor pagination on GET /knowledge/documents.

This collection needs it more than the others: each document serialises its chunks inline,
so the body is the sum of every chunk's text rather than one row per document. A knowledge
base of any size returns an unbounded payload without `limit`.

Two things are asserted here that were not asserted for /projects:

  - the ordering key is a *total* order. A batch upload can stamp several documents with the
    same `created_at`, and a keyset over a non-unique key silently skips rows at a page
    boundary. There is a test that forces the tie and checks nothing is lost.
  - the non-paginated path is unchanged, including the chunks each document carries.

`client` comes from conftest.py: a real app against a real database.
"""

import re

import pytest
from httpx import AsyncClient

DOCS_PATH = (
    "/api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents"
)


async def _tenant(client: AsyncClient, email: str) -> tuple[str, str, str]:
    """Register, then create the project the knowledge base hangs off."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "DocPager",
            "org_name": f"Org {email}",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    orgs = await client.get("/api/v1/organizations", headers=hdr)
    org_id = orgs.json()[0]["id"]

    proj = await client.post(f"/api/v1/organizations/{org_id}/projects", headers=hdr, json={"name": "KB"})
    assert proj.status_code == 201

    return token, org_id, proj.json()["id"]


async def _seed_documents(
    client: AsyncClient, hdr: dict[str, str], org_id: str, project_id: str, count: int
) -> list[str]:
    ids: list[str] = []
    for i in range(count):
        resp = await client.post(
            DOCS_PATH.format(org_id=org_id, project_id=project_id),
            headers=hdr,
            files={"file": (f"doc-{i}.txt", b"content for the knowledge base", "text/plain")},
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    return ids


def _link(response) -> str | None:
    return response.headers.get("link")


def _target(link: str) -> str:
    match = re.search(r"<([^>]+)>", link)
    assert match, f"Link header has no angle-bracket URI: {link!r}"
    return match.group(1)


# --------------------------------------------------------------------- #
# The non-breaking guarantee
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_without_limit_returns_every_document_and_no_link(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_plain@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 4)

    resp = await client.get(
        DOCS_PATH.format(org_id=org_id, project_id=project_id), headers=hdr
    )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 4
    assert _link(resp) is None


@pytest.mark.asyncio
async def test_the_unpaginated_body_still_carries_chunks(client: AsyncClient):
    """The inline chunks are what make this collection heavy; they must not be dropped."""
    token, org_id, project_id = await _tenant(client, "docs_chunks@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 1)

    resp = await client.get(
        DOCS_PATH.format(org_id=org_id, project_id=project_id), headers=hdr
    )
    document = resp.json()[0]

    # Chunks appear only once ingestion has run; the key point is that the field is still
    # present on the paginated and unpaginated responses alike.
    assert "chunks" in document


@pytest.mark.asyncio
async def test_a_page_the_same_size_as_the_collection_sends_no_link(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_exact@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 2)

    resp = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=2", headers=hdr
    )

    assert len(resp.json()) == 2
    assert _link(resp) is None


@pytest.mark.asyncio
async def test_an_empty_knowledge_base_returns_nothing(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_empty@example.com")
    hdr = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=10", headers=hdr
    )

    assert resp.json() == []
    assert _link(resp) is None


# --------------------------------------------------------------------- #
# The paginated path
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_limit_returns_a_page_and_a_next_link(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_paged@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 5)

    resp = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=2", headers=hdr
    )

    assert len(resp.json()) == 2
    link = _link(resp)
    assert link is not None and 'rel="next"' in link and "limit=2" in link


@pytest.mark.asyncio
async def test_walking_every_page_covers_the_collection_exactly_once(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_walk@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    seeded = await _seed_documents(client, hdr, org_id, project_id, 5)

    collected: list[str] = []
    url: str | None = f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=2"
    pages = 0

    while url is not None:
        resp = await client.get(url, headers=hdr)
        assert resp.status_code == 200
        collected.extend(d["id"] for d in resp.json())
        link = _link(resp)
        url = _target(link) if link else None
        pages += 1
        assert pages < 10, "pagination did not terminate"

    assert len(collected) == len(set(collected)), "a document was served on two pages"
    assert set(collected) == set(seeded)


@pytest.mark.asyncio
async def test_documents_are_newest_first(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_order@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    seeded = await _seed_documents(client, hdr, org_id, project_id, 3)

    resp = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=10", headers=hdr
    )

    assert [d["id"] for d in resp.json()] == list(reversed(seeded))


@pytest.mark.asyncio
async def test_a_link_header_can_be_followed_verbatim(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_verbatim@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 4)

    first = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=2", headers=hdr
    )
    second = await client.get(_target(_link(first)), headers=hdr)

    assert second.status_code == 200
    assert not {d["id"] for d in first.json()} & {d["id"] for d in second.json()}


@pytest.mark.asyncio
async def test_a_row_created_mid_pagination_does_not_shift_the_window(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_insert@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 4)

    first = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=2", headers=hdr
    )
    # Insert after the cursor was issued but before the next page is read.
    await _seed_documents(client, hdr, org_id, project_id, 1)
    second = await client.get(_target(_link(first)), headers=hdr)

    assert not {d["id"] for d in first.json()} & {d["id"] for d in second.json()}


# --------------------------------------------------------------------- #
# The tie case that makes created_at alone unsafe
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_documents_sharing_a_timestamp_are_not_lost_at_a_page_boundary(client: AsyncClient):
    """created_at is not unique. A keyset compared on created_at alone loses rows at the boundary.

    Two documents sharing an instant are both on the same side of a `created_at <` comparison,
    so one is never served. The cursor is compared as a (created_at, id) tuple precisely so this
    cannot happen, and this test is what proves it.
    """
    token, org_id, project_id = await _tenant(client, "docs_tie@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    seeded = await _seed_documents(client, hdr, org_id, project_id, 6)

    # Force every document onto one timestamp, the worst case a batch upload produces.
    changed = await _force_uniform_created_at(seeded)
    assert changed == len(seeded), "the tie was not created, so this test would prove nothing"

    collected: list[str] = []
    url: str | None = f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?limit=2"
    pages = 0

    while url is not None:
        resp = await client.get(url, headers=hdr)
        assert resp.status_code == 200
        collected.extend(d["id"] for d in resp.json())
        link = _link(resp)
        url = _target(link) if link else None
        pages += 1
        assert pages < 10, "pagination did not terminate"

    assert sorted(collected) == sorted(seeded), "a tied document was skipped or repeated"


async def _force_uniform_created_at(document_ids: list[str]) -> int:
    """Collapse the given documents' created_at onto one instant, directly in the database.

    Done outside the API because the API has no legitimate reason to do this; the point is to
    create the tie a real batch upload creates by accident.

    Goes through the ORM rather than raw SQL. The UUID columns render differently per driver,
    so a hand-written `WHERE project_id = :project_id` with a dashed string silently matches
    nothing - which is exactly how this helper became a no-op the first time and left the test
    asserting nothing while reporting success.

    Returns the number of rows changed, and the caller asserts it, so a silent no-op cannot
    masquerade as a passing test again.
    """
    import uuid as _uuid

    from sqlalchemy import update

    from app.core.database import get_session_factory
    from app.models.knowledge import KnowledgeDocument

    async with get_session_factory()() as session:
        result = await session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id.in_([_uuid.UUID(d) for d in document_ids]))
            .values(created_at=_uniform_timestamp())
        )
        await session.commit()
        return result.rowcount or 0


def _uniform_timestamp():
    """A single fixed instant, shared by every document in the tie.

    Deliberately naive: the `created_at` column stores naive datetimes, so a value carrying a
    tzinfo would not compare equal to what the API wrote. Matching the column matters more
    here than the generic rule about timezone-aware defaults.
    """
    import datetime as _dt

    return _dt.datetime(2026, 1, 1, 0, 0, 0)  # noqa: DTZ001 - column is naive


# --------------------------------------------------------------------- #
# Scope and bad input
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pagination_does_not_leak_documents_across_projects(client: AsyncClient):
    token_a, org_a, project_a = await _tenant(client, "docs_tenant_a@example.com")
    hdr_a = {"Authorization": f"Bearer {token_a}"}
    await _seed_documents(client, hdr_a, org_a, project_a, 3)

    # A second project in the same organization, with its own knowledge base.
    proj_b = await client.post(
        f"/api/v1/organizations/{org_a}/projects", headers=hdr_a, json={"name": "KB Two"}
    )
    project_b = proj_b.json()["id"]
    await _seed_documents(client, hdr_a, org_a, project_b, 3)
    b_ids = {
        d["id"]
        for d in (
            await client.get(
                DOCS_PATH.format(org_id=org_a, project_id=project_b), headers=hdr_a
            )
        ).json()
    }

    resp = await client.get(
        f"{DOCS_PATH.format(org_id=org_a, project_id=project_a)}?limit=10", headers=hdr_a
    )

    assert not {d["id"] for d in resp.json()} & b_ids


@pytest.mark.asyncio
async def test_an_unreadable_cursor_is_a_400(client: AsyncClient):
    token, org_id, project_id = await _tenant(client, "docs_badcursor@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    await _seed_documents(client, hdr, org_id, project_id, 1)

    resp = await client.get(
        f"{DOCS_PATH.format(org_id=org_id, project_id=project_id)}?cursor=not-a-cursor",
        headers=hdr,
    )

    assert resp.status_code == 400
    assert "cursor" in resp.json()["detail"].lower()


def test_limit_is_optional_and_bounded_in_the_published_schema():
    """A default would silently truncate every existing caller."""
    from app.main import app

    path = "/api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents"
    params = app.openapi()["paths"][path]["get"]["parameters"]
    by_name = {p["name"]: p for p in params}

    assert "default" not in by_name["limit"]
    assert by_name["limit"]["schema"]["anyOf"][0]["minimum"] == 1
    assert by_name["limit"]["schema"]["anyOf"][0]["maximum"] == 100
    assert "default" not in by_name["cursor"]


def test_the_response_is_still_declared_as_an_array():
    from app.main import app

    path = "/api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents"
    schema = app.openapi()["paths"][path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert schema["type"] == "array"
