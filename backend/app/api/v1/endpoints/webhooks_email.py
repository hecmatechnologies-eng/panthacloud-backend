"""The email webhook (ADR-004).

One route, ``POST /webhooks/email``, authenticated by an Svix signature over the raw body.

**Authenticate before anything else, and refuse without a configured secret.** The check and the
reasons for it are in :mod:`app.channels.email.provider`; the short version is that this endpoint
invents guests' conversations, so anyone who can post to it can make the assistant answer as a guest
and spend a tenant's quota.

**Always answer 200 once the signature is good**, including when there is nothing to answer - a
delivery receipt, a bounce, an auto-reply, an address we do not serve. Anything else puts the sender
into a retry loop against us. Acknowledging is reserved for authentication, where a 200 would mean
*we did not check who you are*.

**An email arrives in two pieces.** The alert carries metadata only; the body needs a second call to
the provider. Both are resolved before a conversation is created, so nothing downstream knows a
message arrived in halves.

**The reply is sent after the turn completes**, from the address the guest wrote to, in their thread.
If sending fails the transcript still holds the turn and the guest's own message - which is what
lets staff see it - and the failure is logged rather than raised, because raising would tell the
provider to retry a message that was already answered.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.channels.email import inbound as inbound_rules
from app.channels.email.provider import (
    EmailProviderError,
    InboundEmail,
    WebhookSignatureError,
    fetch_email,
    send_reply,
    verify_webhook,
)
from app.core.config import settings
from app.core.database import get_db
from app.runtime.chat import ChatReply, handle_channel_message
from app.runtime.resolver import TenantResolutionError, resolve_channel_tenant

router = APIRouter(tags=["Webhooks"])

logger = logging.getLogger("fussion.webhooks.email")

#: The alert names the message; the body costs a second call, so it is not unbounded. Generous for a
#: received email, low enough that hashing an arbitrary upload is not a cheap denial of service.
MAX_BODY_BYTES = 1 * 1024 * 1024


async def _send_reply_after_delay(
    email: InboundEmail, reply: ChatReply, delay_seconds: int
) -> None:
    """Send the reply once the provider has already been told everything went fine.

    **Why this runs in the background rather than inside the request.** The wait exists to make the
    reply look less machine-generated, which means it cannot be inside the webhook: the provider's
    own timeout is far shorter than the delay, so blocking would turn every delivery into a retry
    and each retry into another turn. Acknowledging first and sending afterwards is the only ordering
    that satisfies both.

    The cost is honest and worth stating: a process restart during the wait loses the send. That is
    a smaller problem than a retry storm, and the transcript still holds the guest's message and our
    answer so staff can see and resend it.
    """
    if delay_seconds > 0:
        logger.info("email: waiting %ss before replying to %s", delay_seconds, email.email_id)
        await asyncio.sleep(delay_seconds)
    try:
        sent_id = await send_reply(
            # From the address the guest wrote to, so a reply in their thread comes from the hotel.
            from_address=email.to_address,
            to_address=email.from_address,
            subject=inbound_rules.reply_subject(email.subject),
            text=reply.reply,
            reply_to_message_id=email.message_id,
        )
    except (EmailProviderError, httpx.HTTPError):
        # Broader than just the provider's own error, because a transport failure is exactly as
        # unrecoverable here. This runs *after* the provider has been told the delivery succeeded, so
        # there is no retry to fail and no delivery status to change - nothing is watching for this.
        # The only useful action left is a log naming the conversation, which is what staff read when
        # a guest reports silence; letting the exception escape instead would lose that detail.
        #
        # The turn is already committed and visible to staff, so the answer is not lost, only unsent.
        logger.exception("email: turn %s answered but the reply could not be sent", reply.conversation_id)
    else:
        logger.info(
            "email: answered %s on conversation %s (sent as %s)",
            email.email_id,
            reply.conversation_id,
            sent_id,
        )


@router.post(
    "/email",
    summary="Receive an email notification",
)
async def email_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    background: BackgroundTasks,
) -> Response:
    """Authenticate, turn the alert plus its body into a conversation, and answer it."""
    raw = await request.body()

    if len(raw) > MAX_BODY_BYTES:
        return PlainTextResponse(
            content="payload too large", status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        )

    # Before parsing. Deliberately the first thing that can fail the request.
    try:
        verify_webhook(
            raw_body=raw,
            headers=dict(request.headers),
            secret=settings.RESEND_WEBHOOK_SECRET,
        )
    except WebhookSignatureError as exc:
        logger.warning("email: rejected webhook - %s", exc)
        return PlainTextResponse(
            content="signature verification failed", status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        payload: Any = json.loads(raw)
    except ValueError:
        # Authenticated but unreadable; retrying a body we can never parse cannot succeed.
        return Response(status_code=status.HTTP_200_OK)

    if not isinstance(payload, dict):
        return Response(status_code=status.HTTP_200_OK)

    email_id = (payload.get("data") or {}).get("email_id")
    if not email_id:
        # An event type we do not handle. Acknowledged - see the module docstring.
        return Response(status_code=status.HTTP_200_OK)

    try:
        email = await fetch_email(str(email_id))
    except EmailProviderError:
        # The alert is authenticated but the content could not be fetched. Answering non-2xx would
        # have the provider resend the *same* alert, which would fail the same way.
        logger.exception("email: could not fetch %s", email_id)
        return Response(status_code=status.HTTP_200_OK)

    if email is None or not inbound_rules.is_usable(email):
        return Response(status_code=status.HTTP_200_OK)

    try:
        ctx = await resolve_channel_tenant(
            db,
            channel=Channel.EMAIL,
            external_id=inbound_rules.tenant_address(email),
        )
    except TenantResolutionError:
        # An address on our domain that nobody has connected. Refused identically to a bad
        # signature, so the endpoint cannot be used to discover which addresses are in use.
        logger.info("email: no active registration for %s", inbound_rules.tenant_address(email))
        return Response(status_code=status.HTTP_200_OK)

    client_ip = request.client.host if request.client else None

    try:
        reply = await handle_channel_message(
            db,
            ctx=ctx,
            identity=inbound_rules.to_incoming_message(email).identity,
            message=email.text,
            client_ip=client_ip,
            # The provider's own id, so a redelivered alert does not write a second turn.
            message_id=email.email_id,
        )
    except SQLAlchemyError:
        logger.exception("email: could not persist a turn for %s", email.email_id)
        await db.rollback()
        return Response(status_code=status.HTTP_200_OK)
    except Exception:
        # One bad message must not stop the others in a batch, and must not become a retry loop.
        logger.exception("email: turn failed for %s", email.email_id)
        return Response(status_code=status.HTTP_200_OK)

    if reply.is_replay:
        # The provider redelivered a message already answered. The transcript was not duplicated -
        # the unique index absorbed that - but without this the guest gets the same reply again,
        # which is how a provider retrying three times becomes three identical emails.
        logger.info("email: %s already answered; not replying again", email.email_id)
        return Response(status_code=status.HTTP_200_OK)

    # Hand the send to a background task so the wait cannot hold the webhook open. See
    # `_send_reply_after_delay` for why that ordering is the only one that works.
    background.add_task(
        _send_reply_after_delay,
        email,
        reply,
        settings.EMAIL_REPLY_DELAY_SECONDS,
    )

    return Response(status_code=status.HTTP_200_OK)


__all__ = ["router"]