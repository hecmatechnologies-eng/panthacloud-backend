"""Runtime-plane tenant resolution (step B2, FR-108).

Turns an untrusted ``public_key`` and ``Origin`` header into a trusted :class:`TenantContext`,
or refuses. This is the runtime plane's tenancy boundary: every later runtime call resolves its
scope from the returned context, never from anything the caller supplies.

Nothing calls this yet — B1 stored the key and origins, and B4 is the first public endpoint that
consumes them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.origins import normalize_origin
from app.models.allowed_origin import AllowedOrigin
from app.models.project import Project
from app.models.website_integration import WebsiteIntegration

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

    # One query for both conditions. Joining rather than branching means an unknown key and an
    # unregistered origin take the same path and cannot be told apart by response or code path.
    stmt = (
        select(
            WebsiteIntegration.id,
            WebsiteIntegration.project_id,
            Project.organization_id,
        )
        .join(Project, Project.id == WebsiteIntegration.project_id)
        .join(AllowedOrigin, AllowedOrigin.integration_id == WebsiteIntegration.id)
        .where(
            WebsiteIntegration.public_key == public_key,
            AllowedOrigin.origin == canonical_origin,
        )
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise TenantResolutionError()

    integration_id, project_id, organization_id = row
    return TenantContext(
        organization_id=organization_id,
        project_id=project_id,
        integration_id=integration_id,
        origin=canonical_origin,
    )
