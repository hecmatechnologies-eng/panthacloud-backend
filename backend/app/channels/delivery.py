"""Outbound delivery for a channel message (ADR-004).

The other half of the round trip, and the half that turns a guest writing into silence into a
conversation. Per ADR-004 delivery is the *adapter's* job, not the runtime's: the widget streams
with a lagged guard, WhatsApp sends one complete message, and a shared send path would have made
the guarded stream optional.

**Two things here are deliberate refusals rather than best-effort sends.**

*The 24-hour window.* Outside 24 hours after a guest's last inbound message, WhatsApp does not
permit free-form replies - a hotel desk following up on a quote three days later is the canonical
case, and it is exactly what the Follow-up tab is for. Sending anyway does not "probably work"; it
is rejected by the provider and, left unhandled, shows up in the transcript as a delivered message
nobody received. :class:`OutboundWindowClosed` makes that a decision the caller can surface, and
the cure (an approved template) is a product decision that has not been made yet.

*No credentials, no send.* If a registration has neither its own token nor a platform token
configured, this raises rather than quietly skipping. A send that silently does nothing is the
failure mode that gets discovered by a guest.

**Token precedence.** A tenant onboarded via Embedded Signup has its own system-user token, stored
encrypted on their registration; that wins. The platform token is the fallback for a number that has
not been onboarded individually, which is the state a Development-tier install is in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.config import settings
from app.core.secrets import secret_store
from app.models.channel_registration import ChannelRegistration

logger = logging.getLogger("fussion.channels.delivery")

#: WhatsApp closes the free-form customer-service window 24 hours after the guest's last message.
CUSTOMER_SERVICE_WINDOW = 24 * 60 * 60


class DeliveryError(Exception):
    """A message could not be handed to the provider."""


class OutboundWindowClosed(DeliveryError):
    """More than 24 hours since the guest last wrote.

    Not retryable: the same request keeps failing until a template is used instead. A caller that
    retries on this will burn its rate limit and delay the message that *would* have worked.
    """


class ChannelNotRegistered(DeliveryError):
    """No active registration claims this business number."""


class DeliveryStatus(str, Enum):
    """The outcome of a send, as this module can tell without a receipt.

    Deliberately not the provider's ``sent``/``delivered``/``read`` vocabulary. Those are reported
    asynchronously on the status webhook, which is not implemented yet; claiming ``delivered`` here
    would assert something nobody has verified. ``ACCEPTED`` means "the provider took it", which is
    exactly what a 2xx on the send call means.
    """

    ACCEPTED = "accepted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: DeliveryStatus
    #: The provider's message id, on success.
    message_id: str | None = None
    #: A human-readable reason, on failure. Never contains guest content.
    detail: str | None = None


def _within_window(last_inbound_at: datetime | None) -> bool:
    """True when a free-form reply is still permitted.

    No known inbound timestamp is treated as *outside* the window. Guessing the other way would let
    an unbounded message go to a guest who is unreachable, and the failure would only appear as a
    provider rejection.
    """
    if last_inbound_at is None:
        return False
    aware = last_inbound_at if last_inbound_at.tzinfo else last_inbound_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - aware).total_seconds() < CUSTOMER_SERVICE_WINDOW


async def _credentials(db: AsyncSession, phone_number_id: str) -> tuple[str, str]:
    """Return ``(phone_number_id, access_token)`` for a registered business number.

    The tenant's own token is preferred and decrypted on demand; the platform token is the
    fallback. Decryption failure is not swallowed - a registration whose ciphertext cannot be read
    is a fault worth surfacing, not a reason to silently send as the platform.
    """
    registration = (
        await db.execute(
            select(ChannelRegistration).where(
                ChannelRegistration.channel == Channel.WHATSAPP,
                ChannelRegistration.phone_number_id == phone_number_id,
                ChannelRegistration.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()

    if registration is None:
        raise ChannelNotRegistered(
            f"no active WhatsApp registration for phone_number_id {phone_number_id!r}"
        )

    if registration.encrypted_access_token:
        try:
            token = secret_store.decrypt_text(registration.encrypted_access_token)
        except Exception as exc:
            raise DeliveryError(
                f"stored access token for {phone_number_id!r} could not be decrypted"
            ) from exc
        return registration.phone_number_id, token

    if settings.WHATSAPP_ACCESS_TOKEN:
        logger.info("whatsapp: sending as platform token for %s", phone_number_id)

    raise DeliveryError(
        f"no access token available for {phone_number_id!r}; the registration has no token of its "
        "own and WHATSAPP_ACCESS_TOKEN is unset"
    )


async def send_text(
    db: AsyncSession,
    *,
    phone_number_id: str,
    to: str,
    text: str,
    last_inbound_at: datetime | None,
) -> DeliveryResult:
    """Send one text message to a guest.

    Refuses with :class:`OutboundWindowClosed` outside the 24-hour customer-service window rather
    than letting the provider reject it.
    """
    if not _within_window(last_inbound_at):
        raise OutboundWindowClosed(
            "the guest last wrote more than 24 hours ago; a free-form reply is not permitted and "
            "an approved message template is required"
        )

    resolved_id, token = await _credentials(db, phone_number_id)

    url = (
        f"{settings.WHATSAPP_GRAPH_BASE_URL}/{settings.WHATSAPP_GRAPH_API_VERSION}"
        f"/{resolved_id}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        # No '+': the documented example shows a bare `to`, and Meta rejects the prefix here.
        "to": to.lstrip("+"),
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise DeliveryError(f"could not reach the Graph API: {exc}") from exc

    if response.status_code >= 400:
        # Provider error bodies can echo guest content back, so only the code is surfaced.
        logger.warning(
            "whatsapp: send rejected with %s", response.status_code, extra={"body": response.text[:500]}
        )
        return DeliveryResult(status=DeliveryStatus.FAILED, detail=f"HTTP {response.status_code}")

    try:
        body = response.json()
    except ValueError:
        body = {}

    return DeliveryResult(
        status=DeliveryStatus.ACCEPTED,
        message_id=body.get("messages", [{}])[0].get("id") if body.get("messages") else None,
    )


__all__ = [
    "CUSTOMER_SERVICE_WINDOW",
    "ChannelNotRegistered",
    "DeliveryError",
    "DeliveryResult",
    "DeliveryStatus",
    "OutboundWindowClosed",
    "send_text",
]