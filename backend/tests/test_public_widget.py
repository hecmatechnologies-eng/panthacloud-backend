"""Step B · B8 — the served widget bundle (FR-110).

The widget is one asset for every customer, so these tests guard the properties that make it safe to
load on someone else's page: Shadow DOM isolation, no access to the host page's state, and a
cacheable but not permanently-pinned response.
"""

import pytest
from httpx import AsyncClient

WIDGET_URL = "/api/v1/public/widget.js"


@pytest.mark.asyncio
async def test_the_widget_is_served_as_javascript_without_authentication(
    client: AsyncClient,
) -> None:
    resp = await client.get(WIDGET_URL)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/javascript")
    assert "public" in resp.headers["cache-control"]


@pytest.mark.asyncio
async def test_the_widget_is_revalidated_with_an_etag(client: AsyncClient) -> None:
    first = await client.get(WIDGET_URL)
    etag = first.headers["etag"]
    assert etag

    second = await client.get(WIDGET_URL, headers={"If-None-Match": etag})

    assert second.status_code == 304
    assert second.content == b""


@pytest.mark.asyncio
async def test_the_widget_isolates_itself_in_a_shadow_root(client: AsyncClient) -> None:
    """FR-110: the UI must not be reachable from, or reach, the host page's styles or DOM."""
    body = (await client.get(WIDGET_URL)).text

    assert "attachShadow" in body
    assert "data-fussion-key" in body


@pytest.mark.asyncio
async def test_the_widget_reads_nothing_from_the_host_page(client: AsyncClient) -> None:
    """FR-110: no cookies, no storage, no host DOM — the session id is memory-only on purpose.

    Asserted on *usage* rather than on the bare words, so the file may still explain the rule in a
    comment without failing its own guard.
    """
    body = (await client.get(WIDGET_URL)).text

    for forbidden in (
        "localStorage.",
        "localStorage[",
        "sessionStorage.",
        "sessionStorage[",
        "document.cookie",
        "indexedDB.",
    ):
        assert forbidden not in body, f"the widget must not touch {forbidden}"


@pytest.mark.asyncio
async def test_the_widget_calls_the_streamed_endpoint(client: AsyncClient) -> None:
    body = (await client.get(WIDGET_URL)).text

    assert "/api/v1/public/chat/stream" in body
    # It consumes the B7 stream rather than waiting for a whole JSON reply.
    assert "getReader" in body
