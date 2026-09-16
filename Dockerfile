# Fussion Backend - Root Dockerfile for Railway and Container Deployments
#
# Builds the backend and bundles framework skills from the repository root.
# Pinned to uv 0.12.13 matching the lockfile revision.

# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Cache dependency synchronization first
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy backend source code and skills packages
COPY backend/ .
COPY skills/ ./skills/
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"
ENV FORWARDED_ALLOW_IPS=*

# Ensure runtime user owns workspaces directory
RUN useradd --create-home --uid 10001 fussion \
    && mkdir -p /app/data/workspaces \
    && chown -R fussion:fussion /app/data
USER fussion

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips=* --timeout-keep-alive 75
