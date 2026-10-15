"""The WhatsApp webhook (ADR-004).

Two routes, both unauthenticated in the usual sense and both answering to something else instead:

``GET /webhooks/whatsapp``
    Meta's ``hub.*`` verification handshake. Compares the supplied token to
    ``WHATSAPP_VERIFY_TOKEN`` and echoes the challenge.

``POST /webhooks/whatsapp``
    Notifications. Authenticated by ``X-Hub-Signature-256`` over the **raw body** - see
    :mod:`app.channels.whatsapp`, which owns that check and why it must precede parsing.

The raw body is read once, before any JSON library touches it, and the same bytes are used for both
the HMAC and the parse. Parsing first and re-serialising to compute the digest is the standard way
to break this: it fails on any whitespace or key-order difference, and it fails silently - every
delivery simply stops matching, and the hotel's guests get no answers with nothing in the logs.

**Always answers 200 once the signature is good**, even for a payload that yields nothing to answer.
Meta retries anything that is not a 2xx, so raising on an unrecognised message type - an image, a
status receipt, a verification ping - would have it redeliver forever. Work that genuinely fails
is logged and the turn is skipped; refusing to acknowledge delivery is reserved for
authentication, where a 200 would mean *we did not check who you are*.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.channels.whatsapp import (
    SIGNATURE_HEADER,
    WebhookSignatureError,
    parse_webhook,
    verify_signature,
)
from app.core.config import settings
from app.core.database import get_db
from app.runtime.chat import handle_channel_message
from app.runtime.resolver import TenantResolutionError, resolve_channel_tenant

router = APIRouter(tags=["Webhooks"])

logger = logging.getLogger("fussion.webhooks.whatsapp")

#: Ceiling on the body we will hash and parse. A signed WhatsApp text notification is a few hundred
#: bytes; this is generous to admit media notifications while refusing to buffer an arbitrary
#: upload. Checked before parsing, and hashing an unbounded body is how a signature check becomes a
#: denial of service.
MAX_BODY_BYTES = 1 * 1024 * 1024


@router.get(
    "/whatsapp",
    summary="WhatsApp webhook verification handshake",
)
async def whatsapp_verify(request: Request) -> Response:
    """Echo Meta's challenge, but only for the token we configured.

    An unconfigured ``WHATSAPP_VERIFY_TOKEN`` refuses rather than accepting anything: a comparison
    against an empty value would pass whenever Meta sent an empty token, which is a public webhook
    anyone can complete.
    """
    params = request.query_params

    if params.get("hub.mode") != "subscribe":
        return PlainTextResponse(
            content="not a subscription request", status_code=status.HTTP_400_BAD_REQUEST
        )

    expected = settings.WHATSAPP_VERIFY_TOKEN
    if not expected:
        logger.error("whatsapp: verification requested but WHATSAPP_VERIFY_TOKEN is unset")
        return PlainTextResponse(
            content="webhook verification is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if params.get("hub.verify_token") != expected:
        return PlainTextResponse(content="verification failed", status_code=status.HTTP_403_FORBIDDEN)

    return Response(
        content=params.get("hub.challenge", ""),
        media_type="text/plain",
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/whatsapp",
    summary="Receive WhatsApp notifications",
)
async def whatsapp_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Authenticate, parse, and run a turn for every inbound text message."""
    raw = await request.body()

    if len(raw) > MAX_BODY_BYTES:
        return PlainTextResponse(
            content="payload too large", status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        )

    # Before parsing. Deliberately the first thing that can fail the request.
    try:
        verify_signature(
            raw_body=raw,
            signature=request.headers.get(SIGNATURE_HEADER),
            app_secret=settings.WHATSAPP_APP_SECRET,
        )
    except WebhookSignatureError as exc:
        logger.warning("whatsapp: rejected webhook - %s", exc)
        return PlainTextResponse(
            content="signature verification failed", status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        payload: Any = json.loads(raw)
    except ValueError:
        # Authenticated but unreadable. Acknowledged, because retrying a body we will never parse
        # cannot succeed.
        return Response(status_code=status.HTTP_200_OK)

    if not isinstance(payload, dict):
        return Response(status_code=status.HTTP_200_OK)

    inbound = parse_webhook(payload)
    if not inbound:
        return Response(status_code=status.HTTP_200_OK)

    client_ip = request.client.host if request.client else None

    for message in inbound:
        # A group id is not a person; keying a session on it would merge every member's messages
        # into one "guest" and answer the room.
        if message.is_group or not message.addressed_to_business:
            continue
        await _handle_one(db, message, client_ip=client_ip)

    return Response(status_code=status.HTTP_200_OK)


async def _handle_one(db: AsyncSession, message: Any, *, client_ip: str | None) -> None:
    """Run one turn, refusing to let a failure escape.

    Best-effort by design. Meta retries the *whole* delivery on a non-2xx, so raising here would
    re-run every message in the batch including ones already answered - each retry duplicating
    turns. One bad message therefore cannot stop the others, and its failure is logged rather than
    propagated.
    """
    try:
        ctx = await resolve_channel_tenant(
            db,
            channel=Channel.WHATSAPP,
            external_id=message.display_phone_number or message.phone_number_id,
        )
    except TenantResolutionError:
        # Unknown or retired number. Refused identically to a wrong signature, so the webhook
        # cannot be used to discover which numbers are registered.
        logger.info("whatsapp: no active registration for %s", message.phone_number_id)
        return

    try:
        reply = await handle_channel_message(
            db,
            ctx=ctx,
            identity=message.to_incoming_message().identity,
            message=message.text,
            client_ip=client_ip,
            # The wamid, so a provider retry resolves to the row already written rather than
            # appending a second copy of the same turn to the guest's transcript.
            message_id=message.message_id,
        )
    except SQLAlchemyError:
        logger.exception("whatsapp: could not persist a turn for %s", message.message_id)
        await db.rollback()
        return
    except Exception:
        logger.exception("whatsapp: turn failed for %s", message.message_id)
        return

    logger.info(
        "whatsapp: answered %s on conversation %s", message.message_id, reply.conversation_id
    )


__all__ = ["router"]