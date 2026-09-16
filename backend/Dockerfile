# Backend image (step B8 deployment preparation).
#
# Two things this file has to get right that a default Python build would not:
#
#   1. `git` is a *runtime* dependency, not a build one. The analyst clones the customer's
#      repository (`app/services/analysis/clone.py`), so the image needs git on PATH.
#   2. The development entrypoint is not used here. `run_dev.py` installs Windows' SelectorEventLoop
#      because psycopg's async driver cannot use Proactor — a Windows-only workaround. On Linux the
#      default loop works, so production runs uvicorn directly.
#
# The widget bundle ships with the image as a package asset (`app/runtime/widget/fussion-widget.js`),
# which is why there is no separate frontend build step for it.

# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned to the uv that produced `uv.lock` (revision 3). An older uv than the one that wrote the
# lock is the classic way to make `uv sync --frozen` fail inside an image that built fine locally.
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, so a source change does not re-resolve them. The lockfile is the source of
# truth: `--frozen` refuses to update it, which keeps a deploy reproducible.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

# Trust the platform proxy's X-Forwarded-For. Without this uvicorn only trusts 127.0.0.1, so
# `request.client.host` becomes the *proxy's* address and the runtime's per-IP rate limit collapses
# into a single global bucket for every visitor (app/runtime/chat.py).
#
# The trade-off is explicit: a direct caller could spoof the header. The service is reachable only
# through the platform edge, and the integration, organization and session scopes are derived
# server-side, so IP remains the cheapest shed rather than the only one.
ENV FORWARDED_ALLOW_IPS=*

# The analysis clones into WORKSPACE_BASE_DIR (default ./data/workspaces). Create it owned by the
# runtime user, so the container never needs to run as root to write there.
RUN useradd --create-home --uid 10001 fussion \
    && mkdir -p /app/data/workspaces \
    && chown -R fussion:fussion /app/data
USER fussion

EXPOSE 8000
# Shell form so $PORT (injected by the platform) is honoured, with 8000 as the local default.
CMD uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips=* --timeout-keep-alive 75
