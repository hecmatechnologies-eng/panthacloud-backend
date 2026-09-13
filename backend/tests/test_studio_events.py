"""Step C · C13 — the Studio event stream releases its session before streaming.

A server-sent-events connection outlives a request. The stream is authorized by
`authorize_project_stream`, which resolves and closes its session before the response begins, and
the generator then opens a short-lived session per poll (CLAUDE.md §3.6). These tests cover the
authorization path and the structural guarantee that the route holds no session dependency.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Self

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import AsyncClient

from app.api.deps import authorize_project_stream
from app.core.database import get_db


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


async def create_project(client: AsyncClient, token: str, org_id: str, name: str) -> str:
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "slug": name.lower().replace(" ", "-")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_authorize_project_stream_returns_the_trusted_project(client: AsyncClient) -> None:
    token, org_id = await register_user(client, "c13_ok@example.com", "C13Ok")
    proj_id = await create_project(client, token, org_id, "C13 Ok")

    result = await authorize_project_stream(uuid.UUID(org_id), uuid.UUID(proj_id), _creds(token))

    assert str(result) == proj_id


@pytest.mark.asyncio
async def test_authorize_project_stream_refuses_a_foreign_project(client: AsyncClient) -> None:
    token, org_id = await register_user(client, "c13_a@example.com", "C13A")
    proj_id = await create_project(client, token, org_id, "C13 A")
    other_token, _ = await register_user(client, "c13_b@example.com", "C13B")

    with pytest.raises(HTTPException) as exc:
        await authorize_project_stream(uuid.UUID(org_id), uuid.UUID(proj_id), _creds(other_token))

    assert exc.value.status_code == 404  # anti-enumeration, not 403


@pytest.mark.asyncio
async def test_authorize_project_stream_requires_credentials() -> None:
    with pytest.raises(HTTPException) as exc:
        await authorize_project_stream(uuid.uuid4(), uuid.uuid4(), None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_stream_route_requires_authentication(client: AsyncClient) -> None:
    token, org_id = await register_user(client, "c13_anon@example.com", "C13Anon")
    proj_id = await create_project(client, token, org_id, "C13 Anon")

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/projects/{proj_id}/events/stream"
    )
    assert resp.status_code == 401


def _dependency_calls(dependant) -> set[object]:
    calls: set[object] = set()
    for sub in dependant.dependencies:
        calls.add(sub.call)
        calls |= _dependency_calls(sub)
    return calls


class _Event:
    """A stand-in for an AuditEvent row; only the fields `_frame` reads."""

    def __init__(self, index: int) -> None:
        self.id = uuid.uuid4()
        self.event_type = "test.event"
        self.payload = {"index": index}
        self.created_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index)


class _Result:
    def __init__(self, rows: list[_Event]) -> None:
        self._rows = rows

    def scalars(self) -> Self:
        return self

    def all(self) -> list[_Event]:
        return self._rows


class _Session:
    def __init__(self, rows: list[_Event]) -> None:
        self._rows = rows
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self.closed = True
        return False

    async def execute(self, _stmt: object) -> _Result:
        return _Result(self._rows)


class _Request:
    """A request that stays connected for one poll, then disconnects."""

    def __init__(self) -> None:
        self._disconnected = [False, True]

    async def is_disconnected(self) -> bool:
        return self._disconnected.pop(0) if self._disconnected else True


@pytest.mark.asyncio
async def test_event_generator_holds_no_session_across_a_yield(monkeypatch) -> None:
    """The slice's central claim: a session is opened per poll and closed before anything is sent.

    A regression that moved `_frame` outside the `async with`, or that held one session across the
    loop, would keep a session open at a yield and fail here.
    """
    from app.api.v1.endpoints import studio_events as mod

    sessions: list[_Session] = []

    def factory() -> _Session:
        session = _Session([_Event(0)])
        sessions.append(session)
        return session

    monkeypatch.setattr(mod, "get_session_factory", lambda: factory)

    response = await mod.stream_project_events(_Request(), uuid.uuid4())

    frames: list[str] = []
    async for frame in response.body_iterator:
        frames.append(frame)
        assert sessions and all(s.closed for s in sessions), (
            "a session was open while a frame was yielded"
        )

    assert frames, "the stream produced no frames"
    assert len(sessions) >= 2, "the poll loop did not open its own session"



def test_stream_route_holds_no_session_dependency() -> None:
    """The regression guard for C13: no `get_db` in the route's dependency tree.

    A `yield` dependency is closed only after the response completes, so if `get_db` were in this
    tree the connection would hold a pooled session for the stream's whole life.
    """
    from app.api.v1.endpoints.studio_events import router as studio_router

    route = next(r for r in studio_router.routes if r.path.endswith("/events/stream"))
    assert get_db not in _dependency_calls(route.dependant)
