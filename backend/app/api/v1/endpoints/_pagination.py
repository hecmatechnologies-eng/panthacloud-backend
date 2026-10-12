"""Keyset cursor pagination.

Deliberately not the `{items, next_cursor}` envelope in api-routing-standards.md §3.5. That shape
is better designed, but every one of these collections is already served as a bare JSON array to
the Studio's resources.ts and to deployed integrations. Changing it would be a breaking change to
eleven live endpoints in order to satisfy a document written a week ago.

So the response body does not move. Instead:

  - `limit` and `cursor` are accepted as optional query parameters; omitting both returns exactly
    what it returned before, which is what keeps this non-breaking.
  - the next page is advertised in a `Link` header per RFC 8288, the pattern GitHub uses.

Keyset rather than offset. An offset shifts under concurrent inserts, which produces duplicated
and skipped rows - precisely in the live activity feeds this product has. A cursor is anchored to
the last row seen, so a row inserted mid-pagination does not shift the window.

The cursor is opaque base64 over the ordering key. Opaque matters: it means the encoding is an
implementation detail we may change without it being a contract change.
"""

import base64
import binascii
import datetime as dt
import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, status


class InvalidCursor(Exception):
    """The client sent a cursor this server cannot interpret."""


def encode_cursor(values: dict[str, Any]) -> str:
    raw = json.dumps(values, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding)
        decoded = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor("cursor is not readable") from exc
    if not isinstance(decoded, dict):
        raise InvalidCursor("cursor is not an object")
    if not decoded:
        # We never issue an empty cursor, so an empty object is a forgery or a client bug.
        # Rejecting here means callers need not rely on a later KeyError to notice.
        raise InvalidCursor("cursor is empty")
    return decoded


def parse_timestamp(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidCursor("cursor timestamp is not ISO-8601") from exc
    raise InvalidCursor("cursor timestamp is missing")


def cursor_http_error() -> HTTPException:
    """400, not 422. The request was well-formed; the cursor value was not one we issued."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The cursor is not valid. Restart pagination without a cursor.",
    )


def next_link(
    *,
    request_path: str,
    params: dict[str, Any],
    limit: int,
    cursor: str,
) -> str:
    """An RFC 8288 Link header value naming the next page."""
    query = {k: v for k, v in params.items() if v is not None and k not in {"cursor"}}
    query["limit"] = limit
    query["cursor"] = cursor
    return f'<{request_path}?{urlencode(query)}>; rel="next"'


def apply_page(rows: Sequence[Any], limit: int, last_cursor: str, path: str, params: dict[str, Any]) -> str | None:
    """Trim an over-fetched page and return the Link header value, or None when exhausted.

    Callers fetch limit + 1 rows: the extra row is how we know another page exists without a
    second COUNT query, which on a large table costs more than the page itself.
    """
    if len(rows) <= limit:
        return None
    return next_link(request_path=path, params=params, limit=limit, cursor=last_cursor)