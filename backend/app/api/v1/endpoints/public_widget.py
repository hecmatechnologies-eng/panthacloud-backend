"""Serve the assistant widget (step B8, FR-110).

One asset for every customer: a fix reaches all of them at once, instead of a pull request per
repository. It is a package asset rather than generated code, which is what keeps the widget source
independent of `artifacts.py` (`STEP-B-SLICES.md`, B8 notes).

A classic `<script src>` is not subject to CORS, so the file itself needs no origin check. Its
*calls* do, and those go to `/public/chat/stream`.
"""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["Public Widget"])

_WIDGET_PATH = Path(__file__).resolve().parents[3] / "runtime" / "widget" / "fussion-widget.js"

# Read once: the file cannot change while the process runs, and a widget request must not touch disk.
_source: str | None = None
_etag: str | None = None


def _load() -> tuple[str, str]:
    global _source, _etag
    if _source is None:
        # Served straight from source, uncompressed on disk and gzipped in transit.
        #
        # This used to prefer a checked-in `fussion-widget.min.js` when present. Nothing in the
        # repository could produce that file, so it was a hand-maintained copy that had already
        # drifted from the source: every widget fix was being written and then silently not
        # shipped, because the stale bundle won the lookup. A build artifact nobody can
        # regenerate is a worse trade than ~4KB of gzip.
        _source = _WIDGET_PATH.read_text(encoding="utf-8")
        digest = hashlib.sha256(_source.encode("utf-8")).hexdigest()[:32]
        _etag = f'"{digest}"'
    return _source, _etag


@router.get("/widget.js", include_in_schema=False)
async def public_widget(request: Request) -> Response:
    source, etag = _load()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return Response(
        content=source,
        media_type="application/javascript; charset=utf-8",
        headers={
            # Short on purpose: the file is small, and a widget fix must not stay pinned in a
            # customer's browser cache for a day.
            "Cache-Control": "public, max-age=300",
            "ETag": etag,
        },
    )
