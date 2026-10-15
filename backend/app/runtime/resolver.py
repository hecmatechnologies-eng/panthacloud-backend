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

from app.channels.base import Channel, normalize_external_id
from app.core.origins import (
    get_origin_aliases,
    is_preview_origin,
    is_private_or_loopback_origin,
    normalize_origin,
)
from app.models.allowed_origin import AllowedOrigin
from app.models.channel_registration import ChannelRegistration
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

    Built from server state and nowhere else - by :func:`resolve_tenant` for a widget, or by
    :func:`channel_context` for a messaging channel. Frozen so no later stage, model output in
    particular, can widen its scope.

    ``integration_id`` and ``origin`` are the *widget* identity, and are ``None`` for a channel
    turn: a WhatsApp guest has no integration behind them and no browser origin. That absence is
    meaningful rather than missing data - ``project_id`` is the tenancy anchor, and the other two
    are provenance. Code that needs to bound a request by widget reads these; code that needs to
    bound it by tenant reads ``project_id``.
    """

    organization_id: uuid.UUID
    project_id: uuid.UUID
    integration_id: uuid.UUID | None
    origin: str | None


def channel_context(
    *, organization_id: uuid.UUID, project_id: uuid.UUID
) -> TenantContext:
    """A context for a turn that arrived over a messaging channel.

    Kept next to the dataclass so that every ``TenantContext`` in the codebase is constructed in one
    place. The caller must have already resolved the speaker to a project - by phone number,
    handle, or email address, depending on the channel - and tenancy for an unresolvable speaker is
    the refusal path in ``app.channels.resolve``, not a default.

    There is deliberately no way to supply an integration or an origin here. They identify a
    browser, and a channel turn has neither; a constructor that accepted them would let an adapter
    invent a widget identity for a phone-numbered guest and quietly put the conversation in the
    wrong place.
    """
    return TenantContext(
        organization_id=organization_id,
        project_id=project_id,
        integration_id=None,
        origin=None,
    )


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


#: Channels this module can route. EMAIL is absent deliberately: an inbound email is addressed to a
#: routing address the tenant controls, but a *reply* comes from whatever address the guest typed,
#: which matches no registration. Routing replies therefore has to work from the session, not from
#: the address, and that design is not written. Refusing is honest; accepting the To: header alone
#: would silently drop every guest who replies from a different address.
_ROUTABLE_CHANNELS = frozenset({Channel.WHATSAPP, Channel.TELEGRAM, Channel.SMS})


async def resolve_channel_tenant(
    db: AsyncSession,
    *,
    channel: Channel,
    external_id: str,
) -> TenantContext:
    """Resolve the **business** address to a :class:`TenantContext`, or refuse.

    The channel counterpart to :func:`resolve_tenant`, and the question a webhook arrives asking.
    ``AllowedOrigin`` answers the same question for a browser; this answers it for an address
    somebody dialled.

    .. warning::
       ``external_id`` here is the **business's** number - the one the tenant claimed on the
       ``ChannelRegistration`` row - and **not** the guest's ``wa_id``. This docstring previously
       said ``wa_id``, which was wrong in a way that would have been invisible: an adapter that
       followed it would look up every guest's number in ``channel_registrations``, match nothing,
       and route zero messages while every test stayed green. The confusion is easy to fall into
       because a WhatsApp webhook carries *both*, and they are different things:

       - ``value.metadata.display_phone_number`` / ``phone_number_id`` - **our** number. Identifies
         the tenant. This is what belongs in ``external_id``.
       - ``messages[].from`` (the ``wa_id``) - the **guest's**. Identifies the person, and is what
         the *session* is keyed by, not the registration.

       The two are kept apart in the adapter: ``WhatsAppInbound.phone_number_id`` /
       ``display_phone_number`` for this lookup, and ``WhatsAppInbound.wa_id`` for
       :func:`app.channels.sessions.get_or_create_session`.

    Raises the same :class:`TenantResolutionError` as the widget path, and for the same reason: a
    caller must not be able to learn whether an address is registered. "No such number" and "that
    number belongs to someone else" are the same refusal to the outside, and the difference is
    already recorded by whether a session was opened.
    """
    if channel not in _ROUTABLE_CHANNELS:
        raise TenantResolutionError()

    canonical = normalize_external_id(channel, external_id)
    if not canonical:
        # An empty address would find nothing, which is the right outcome - but as a deliberate
        # refusal rather than as a query that happens to miss for a structural reason.
        raise TenantResolutionError()

    registration = (
        await db.execute(
            select(ChannelRegistration).where(
                ChannelRegistration.channel == channel,
                ChannelRegistration.external_identifier == canonical,
            )
        )
    ).scalar_one_or_none()

    # An inactive registration still holds its address, so it still answers here. Refusing is what
    # stops a retired number from being handed to a different tenant while the row sits around.
    if registration is None or not registration.is_active:
        raise TenantResolutionError()

    return channel_context(
        organization_id=registration.organization_id,
        project_id=registration.project_id,
    )
