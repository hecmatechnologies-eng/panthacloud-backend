"""Runtime-plane tenant resolution (step B2, FR-108).

Turns an untrusted ``public_key`` and ``Origin`` header into a trusted :class:`TenantContext`,
or refuses. This is the runtime plane's tenancy boundary: every later runtime call resolves its
scope from the returned context, never from anything the caller supplies.

Supports:
- Verified registered origins.
- Ephemeral preview origins (e.g. *.vercel.app) with provisional auto-registration.
- Fast-deploy self-healing fallback when customer deploys before webhook delivery.
- Origin telemetry (updates last_seen_at).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.origins import (
    get_origin_aliases,
    is_preview_origin,
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

logger = logging.getLogger("fussion.resolver")

# One message for every refusal cause. An unknown key, an unregistered origin and an origin
# registered to a different integration must be indistinguishable to the caller (FR-108): a
# distinct message would let an attacker enumerate which public keys and origins exist.
_REFUSAL_MESSAGE = "Unknown client key or unregistered origin."


class TenantResolutionError(Exception):
    """The request could not be attributed to a tenant. Carries no distinguishing detail."""

    def __init__(self) -> None:
        super().__init__(_REFUSAL_MESSAGE)


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Trusted tenancy for one runtime request.

    Constructed only by :func:`resolve_tenant`, from server state. Frozen so no later stage —
    model output in particular — can widen its scope.
    """

    organization_id: uuid.UUID
    project_id: uuid.UUID
    integration_id: uuid.UUID
    origin: str


async def resolve_tenant(
    db: AsyncSession,
    public_key: str | None,
    origin: str | None,
) -> TenantContext:
    """Resolve ``public_key`` + ``origin`` to a :class:`TenantContext`, or refuse.

    The key identifies the integration; the origin must be one registered for *that*
    integration. Both are required. A missing, empty or malformed value is refused exactly like
    a mismatch, so no input shape reveals whether the other one was valid.
    """
    if not public_key or not origin:
        raise TenantResolutionError()

    try:
        # Same canonicaliser B1 stored with (app.core.origins). A second implementation here
        # would let the registered and presented forms drift apart.
        canonical_origin = normalize_origin(origin)
    except ValueError:
        # A malformed Origin is a failed match, not a validation error: the caller is a browser,
        # not our own UI, and FR-108 requires one indistinguishable refusal.
        raise TenantResolutionError() from None

    # Fast path: Query for existing registered AllowedOrigin
    stmt = (
        select(
            WebsiteIntegration.id,
            WebsiteIntegration.project_id,
            Project.organization_id,
            AllowedOrigin.id.label("origin_id"),
        )
        .join(Project, Project.id == WebsiteIntegration.project_id)
        .join(AllowedOrigin, AllowedOrigin.integration_id == WebsiteIntegration.id)
        .where(
            WebsiteIntegration.public_key == public_key,
            AllowedOrigin.origin == canonical_origin,
        )
    )
    row = (await db.execute(stmt)).first()
    if row is not None:
        integration_id, project_id, organization_id, origin_id = row
        try:
            origin_obj = await db.get(AllowedOrigin, origin_id)
            if origin_obj is not None:
                origin_obj.last_seen_at = datetime.now(UTC)
                await db.commit()
        except SQLAlchemyError:
            await db.rollback()

        return TenantContext(
            organization_id=organization_id,
            project_id=project_id,
            integration_id=integration_id,
            origin=canonical_origin,
        )

    # If not registered, enforce strict sanitization: loopback/private/tunnel domains cannot auto-bind.
    if is_private_or_loopback_origin(canonical_origin):
        raise TenantResolutionError()

    # Look up integration by public key
    intg_stmt = (
        select(WebsiteIntegration, Project.organization_id)
        .join(Project, Project.id == WebsiteIntegration.project_id)
        .where(WebsiteIntegration.public_key == public_key)
    )
    intg_row = (await db.execute(intg_stmt)).first()
    if intg_row is None:
        raise TenantResolutionError()

    integration, organization_id = intg_row

    # Determine eligibility for provisional auto-discovery
    is_preview = is_preview_origin(canonical_origin)
    should_provisional_bind = False
    source = "auto_provisional"

    if is_preview:
        should_provisional_bind = True
        source = "preview_provisional"
    elif integration.status in (
        WebsiteIntegrationStatus.PR_MERGED,
        WebsiteIntegrationStatus.DEPLOYED,
    ):
        should_provisional_bind = True
        source = "auto_provisional"
    elif integration.status == WebsiteIntegrationStatus.PR_CREATED:
        # Self-healing check: Has the PR been merged on GitHub even if webhook was delayed?
        try:
            run_stmt = (
                select(IntegrationRun)
                .where(IntegrationRun.integration_id == integration.id)
                .order_by(IntegrationRun.created_at.desc())
            )
            run = (await db.execute(run_stmt)).scalars().first()
            if run and run.pull_request_number:
                from app.services.integration.credentials import resolve_github_token
                from app.services.integration.github import get_git_provider

                provider = get_git_provider()
                token = None
                try:
                    token = await resolve_github_token(db, integration)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Could not resolve github token for self-healing: %s", exc)
                pr_data = await provider.get_pull_request(
                    integration.repository_owner,
                    integration.repository_name,
                    run.pull_request_number,
                    token,
                )
                if pr_data and (pr_data.get("merged") or pr_data.get("status") == "merged"):
                    integration.status = WebsiteIntegrationStatus.PR_MERGED
                    run.status = WebsiteIntegrationStatus.PR_MERGED
                    should_provisional_bind = True
                    source = "auto_provisional"
        except Exception:
            logger.debug("PR status check fallback encountered an error", exc_info=True)

    if should_provisional_bind:
        aliases = get_origin_aliases(canonical_origin)
        for alias in aliases:
            existing_stmt = select(AllowedOrigin).where(
                AllowedOrigin.integration_id == integration.id,
                AllowedOrigin.origin == alias,
            )
            existing = (await db.execute(existing_stmt)).scalar_one_or_none()
            if existing is None:
                db.add(
                    AllowedOrigin(
                        integration_id=integration.id,
                        origin=alias,
                        is_verified=False,
                        source=source,
                        last_seen_at=datetime.now(UTC),
                    )
                )
        try:
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()

        return TenantContext(
            organization_id=organization_id,
            project_id=integration.project_id,
            integration_id=integration.id,
            origin=canonical_origin,
        )

    raise TenantResolutionError()
