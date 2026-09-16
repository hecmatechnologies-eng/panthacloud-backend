"""Per-origin CORS for the public surface (step B8, FR-107, CLAUDE.md §4.11).

The app's global ``CORSMiddleware`` allows the Studio's origins and nothing else. A customer's site
is a different origin per tenant, and ``allow_origins=["*"]`` is forbidden in production — so the
public routes carry their own policy: the request's ``Origin`` must be one registered for *some*
integration.

A CORS preflight carries no body, so the public key is not available when the browser asks; the
answer can only come from the Origin alone. The key/origin **pair** is still enforced by the tenant
resolver on the real request — this middleware only decides whether the browser is allowed to read
the response at all, which is why a wrong origin still gets a 403 from the endpoint.

Written as a pure ASGI middleware rather than ``BaseHTTPMiddleware``: the latter wraps every
response in a task group, and the public chat is a stream (step B7).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from starlette.datastructures import MutableHeaders

from app.core.database import get_session_factory
from app.core.origins import normalize_origin
from app.models.allowed_origin import AllowedOrigin

logger = logging.getLogger("fussion.api.public_cors")

PUBLIC_PREFIX = "/api/v1/public/"
ALLOWED_METHODS = "POST, OPTIONS"
ALLOWED_HEADERS = "content-type"
# Browsers cache a preflight for this long, which keeps a busy page from re-asking every request.
MAX_AGE_SECONDS = "600"

Scope = dict[str, Any]
Message = dict[str, Any]
Send = Callable[[Message], Awaitable[None]]


class PublicCorsMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Any, send: Send) -> None:
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith(PUBLIC_PREFIX):
            await self.app(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        allowed = origin if await _is_registered(origin) else None

        if scope.get("method") == "OPTIONS":
            await _preflight(send, allowed)
            return

        async def send_with_cors(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(scope=message)
                # Clear first: the global CORSMiddleware has already run and adds
                # `Access-Control-Allow-Credentials: true` to *every* response whenever credentials
                # are enabled for the Studio, whatever the origin. The public surface owns its CORS
                # policy outright.
                _clear(headers)
                if allowed is not None:
                    _apply(headers, allowed)
            await send(message)

        await self.app(scope, receive, send_with_cors)


async def _is_registered(origin: str | None) -> bool:
    """Whether *any* integration has registered this origin.

    A failure to read the database is answered as "not registered": a CORS header that cannot be
    justified must not be sent, and a broken database should surface as a 500 from the endpoint
    rather than as a preflight that quietly grants access.
    """
    if not origin:
        return False
    try:
        canonical = normalize_origin(origin)
    except ValueError:
        return False
    try:
        session_factory = get_session_factory()
        async with session_factory() as db:
            stmt = select(AllowedOrigin.id).where(AllowedOrigin.origin == canonical).limit(1)
            return (await db.execute(stmt)).scalar_one_or_none() is not None
    except Exception:
        logger.exception("Could not check whether origin %r is registered.", canonical)
        return False


_CORS_HEADERS = (
    "Access-Control-Allow-Origin",
    "Access-Control-Allow-Credentials",
    "Access-Control-Allow-Methods",
    "Access-Control-Allow-Headers",
)


def _clear(headers: MutableHeaders) -> None:
    for name in _CORS_HEADERS:
        if name in headers:
            del headers[name]


def _apply(headers: MutableHeaders, origin: str) -> None:
    headers["Access-Control-Allow-Origin"] = origin
    headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
    headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
    # No Access-Control-Allow-Credentials: the public surface authenticates with the key in the
    # body, never a cookie, so the browser must not attach credentials to it.
    headers.append("Vary", "Origin")


async def _preflight(send: Send, origin: str | None) -> None:
    headers = [(b"content-length", b"0")]
    if origin is not None:
        headers += [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"access-control-allow-methods", ALLOWED_METHODS.encode("latin-1")),
            (b"access-control-allow-headers", ALLOWED_HEADERS.encode("latin-1")),
            (b"access-control-max-age", MAX_AGE_SECONDS.encode("latin-1")),
            (b"vary", b"Origin"),
        ]
    await send({"type": "http.response.start", "status": 204, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None
