"""Turning an arrival into the channel-neutral shape the runtime takes.

The split that matters, and the one WhatsApp made obvious:

- **Which hotel** - the address the mail was sent *to*. Matches a ``ChannelRegistration``.
- **Which guest** - the address it came *from*. Keys the conversation.

Never the other way round. A guest replying from an address nobody has seen is normal, and routing
on it would drop the reply; keying the conversation on it would merge every guest who emailed the
hotel into one thread. ``In-Reply-To`` narrows that second case, but only as a tiebreaker within a
single guest's own history - never as a way to decide who a message is from.

**Why the address we match is the receiving one.** Routing has to work for the *first* message, when
there is no thread and no history to consult. Only the recipient identifies the tenant at that point,
which is the same reason a WhatsApp webhook routes on the business number and not the guest's
``wa_id``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.channels.base import Channel, ChannelIdentity, IncomingMessage, normalize_external_id
from app.channels.email.provider import InboundEmail

logger = logging.getLogger("fussion.channels.email.inbound")


def tenant_address(email: InboundEmail) -> str:
    """The address this mail was sent to, in the form registrations are stored in.

    Normalised through the same function :func:`app.channels.base.normalize_external_id` uses for
    registration, because registration and lookup have to land on the same row and two hand-written
    normalisers eventually differ by a character - which silently splits a guest's history.
    """
    return normalize_external_id(Channel.EMAIL, email.to_address)


def guest_address(email: InboundEmail) -> str:
    """The guest's own address, normalised the same way."""
    return normalize_external_id(Channel.EMAIL, email.from_address)


def received_at(email: InboundEmail) -> datetime:
    """When the email arrived, as a timezone-aware datetime.

    Falls back to now rather than a naive value: the timestamp arrives as a provider string in an
    unspecified zone, and a naive datetime compared against an aware one raises ``TypeError`` at some
    point downstream that has no idea this is where it came from.
    """
    if email.received_at:
        try:
            parsed = datetime.fromisoformat(email.received_at)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            logger.debug("email: unparseable timestamp %r", email.received_at)
    return datetime.now(UTC)


def is_usable(email: InboundEmail) -> bool:
    """Whether this email can become a conversation.

    Refused when the tenant or guest address is missing, because without both there is nothing to
    route and nothing to reply to. An auto-reply or a bounce frequently has neither, and answering
    one would put the assistant in a loop with the mail server that sent it.
    """
    if not email.to_address:
        logger.info("email %s: no recipient, skipping", email.email_id)
        return False
    if not email.from_address:
        logger.info("email %s: no sender, skipping (likely a bounce or auto-reply)", email.email_id)
        return False
    if not email.text.strip():
        logger.info("email %s: empty body, skipping", email.email_id)
        return False
    return True


def to_incoming_message(email: InboundEmail) -> IncomingMessage:
    """The channel-neutral shape, keyed on the guest.

    ``message_id`` carries the provider's own id rather than the RFC 5322 ``Message-ID``, because it
    is what ``Message.external_message_id`` deduplicates on: a redelivered alert must resolve to the
    row already written rather than appending a second copy of the same email to the transcript.
    """
    identity = ChannelIdentity(
        channel=Channel.EMAIL,
        external_id=guest_address(email),
        # Unset: a 1:1 email thread *is* the thread. Populating it later is a provider change, not a
        # change here.
        thread_id=None,
    )
    return IncomingMessage(
        identity=identity,
        text=email.text,
        received_at=received_at(email),
        message_id=email.email_id,
        display_name=email.from_name,
        metadata={
            "tenant_address": tenant_address(email),
            "guest_address": guest_address(email),
            "subject": email.subject,
            "rfc_message_id": email.message_id,
            "in_reply_to": email.in_reply_to,
        },
    )


def reply_subject(subject: str) -> str:
    """The subject for our reply.

    Kept identical to the incoming one when it already reads ``Re:``, because repeatedly stacking
    ``Re: Re: Re:`` is the fastest way to make a hotel's inbox unreadable. Only the first is added.
    """
    stripped = (subject or "").strip()
    if not stripped:
        return "Re: your enquiry"
    # Normalised to a single capitalised "Re:" rather than preserving the sender's casing: every
    # client strips Re: before threading, so the casing carries no information, and one consistent
    # prefix is what keeps a folder from filling with "RE: re: RE:".
    if stripped.lower().startswith("re:"):
        return f"Re: {stripped[3:].lstrip()}"
    return f"Re: {stripped}"


__all__ = [
    "guest_address",
    "is_usable",
    "received_at",
    "reply_subject",
    "tenant_address",
    "to_incoming_message",
]