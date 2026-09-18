"""GitHub webhook ingestion endpoint.

Handles GitHub App webhook events:
- pull_request: updates integration status to PR_MERGED on merge.
- deployment_status: extracts deployment environment_url, verifies it,
  automatically registers apex and www sibling aliases, and sets status to DEPLOYED.
"""

import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.origins import (
    get_origin_aliases,
    is_private_or_loopback_origin,
    normalize_origin,
)
from app.models.allowed_origin import AllowedOrigin
from app.models.project import Project
from app.models.website_integration import (
    IntegrationRun,
    WebsiteIntegration,
    WebsiteIntegrationStatus,
)
from app.services.audit import record_audit

logger = logging.getLogger("fussion.webhooks")

router = APIRouter(tags=["Webhooks"])


def _verify_github_signature(body: bytes, signature_header: str | None) -> None:
    """Verify GitHub HMAC-SHA256 signature against settings.GITHUB_APP_WEBHOOK_SECRET."""
    secret = settings.GITHUB_APP_WEBHOOK_SECRET
    if not secret:
        # If secret is unconfigured (e.g. testing/local dev without webhook secret), log warning.
        logger.debug("GITHUB_APP_WEBHOOK_SECRET not configured; skipping signature check.")
        return

    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Hub-Signature-256 header.",
        )

    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        logger.warning("Invalid GitHub webhook HMAC signature received")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub webhook signature verification failed.",
        )


@router.post("/github", summary="Receive GitHub App webhook deliveries")
async def github_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_github_event: Annotated[str | None, Header()] = None,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    body = await request.body()
    _verify_github_signature(body, x_hub_signature_256)

    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body.",
        ) from None

    event = (x_github_event or "").lower()
    logger.info("Received GitHub webhook event: %s (delivery: %s)", event, x_github_delivery)

    if event == "ping":
        return {"status": "pong"}

    if event == "pull_request":
        action = payload.get("action")
        pr_data = payload.get("pull_request") or {}
        merged = bool(pr_data.get("merged", False))
        repo_data = payload.get("repository") or {}
        owner = ((repo_data.get("owner") or {}).get("login") or "").lower()
        repo = (repo_data.get("name") or "").lower()
        pr_number = pr_data.get("number")

        if action == "closed" and merged:
            stmt = select(WebsiteIntegration).where(
                WebsiteIntegration.repository_owner.ilike(owner),
                WebsiteIntegration.repository_name.ilike(repo),
            )
            integrations = (await db.execute(stmt)).scalars().all()
            for integration in integrations:
                integration.status = WebsiteIntegrationStatus.PR_MERGED
                # Also update matching run if exists
                if pr_number:
                    run_stmt = select(IntegrationRun).where(
                        IntegrationRun.integration_id == integration.id,
                        IntegrationRun.pull_request_number == pr_number,
                    )
                    run = (await db.execute(run_stmt)).scalar_one_or_none()
                    if run:
                        run.status = WebsiteIntegrationStatus.PR_MERGED

                proj = (
                    await db.execute(
                        select(Project).where(Project.id == integration.project_id)
                    )
                ).scalar_one_or_none()
                if proj:
                    await record_audit(
                        db,
                        proj.organization_id,
                        integration.project_id,
                        None,
                        "integration.pr.merged",
                        integration.id,
                        {"pr_number": pr_number, "repo": f"{owner}/{repo}"},
                    )
            await db.commit()
            return {"status": "processed", "event": "pull_request.merged"}

    elif event == "deployment_status":
        dep_status = payload.get("deployment_status") or {}
        state = (dep_status.get("state") or "").lower()
        env_url = dep_status.get("environment_url") or dep_status.get("target_url")
        repo_data = payload.get("repository") or {}
        owner = ((repo_data.get("owner") or {}).get("login") or "").lower()
        repo = (repo_data.get("name") or "").lower()

        if state == "success" and env_url:
            try:
                canonical = normalize_origin(env_url)
            except ValueError:
                logger.warning("Invalid environment_url in deployment_status: %s", env_url)
                return {"status": "ignored", "reason": "invalid_origin"}

            if is_private_or_loopback_origin(canonical):
                logger.info("Ignoring loopback/private origin: %s", canonical)
                return {"status": "ignored", "reason": "private_origin"}

            aliases = get_origin_aliases(canonical)

            stmt = select(WebsiteIntegration).where(
                WebsiteIntegration.repository_owner.ilike(owner),
                WebsiteIntegration.repository_name.ilike(repo),
            )
            integrations = (await db.execute(stmt)).scalars().all()
            for integration in integrations:
                integration.status = WebsiteIntegrationStatus.DEPLOYED
                for origin_str in aliases:
                    existing_stmt = select(AllowedOrigin).where(
                        AllowedOrigin.integration_id == integration.id,
                        AllowedOrigin.origin == origin_str,
                    )
                    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
                    if existing is None:
                        db.add(
                            AllowedOrigin(
                                integration_id=integration.id,
                                origin=origin_str,
                                is_verified=True,
                                source="github_deployment",
                            )
                        )
                    else:
                        existing.is_verified = True
                        existing.source = "github_deployment"

                proj = (
                    await db.execute(
                        select(Project).where(Project.id == integration.project_id)
                    )
                ).scalar_one_or_none()
                if proj:
                    await record_audit(
                        db,
                        proj.organization_id,
                        integration.project_id,
                        None,
                        "integration.deployed",
                        integration.id,
                        {"environment_url": env_url, "origins": aliases},
                    )

            await db.commit()
            return {"status": "processed", "event": "deployment_status.success"}

    return {"status": "ignored", "event": event}
