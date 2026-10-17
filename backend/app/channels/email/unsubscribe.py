"""One-click unsubscribe for email (RFC 8058).

**Why this exists, stated plainly.** A guest assistant sends automated replies to addresses that
never asked to hear from us. Gmail treats such mail as bulk by default and, since February 2024,
requires a one-click opt-out from senders at volume. Offering one is also simply the right thing to
do to someone who does not want it.

**The awkward constraint.** RFC 8058 requires the endpoint to work with *no* authentication, because
the request comes from the guest's mail client following a link in the message, and that client has
no session, cookie or key with us. Two consequences follow, and both are deliberate:

- The token must be unguessable. It is 32 bytes from ``secrets.token_urlsafe``; deriving it from a
  row id or an address would let anyone unsubscribe anyone.
- Every response is 200, including for a token that does not exist. A 404 would be an oracle telling
  an attacker which addresses are real customers, which is worth more than the token itself.

**What opting out does and does not do.** It stops automated sends to that guest. It does not delete
the transcript, which is the hotel's record of what was asked. It does not auto-resubscribe someone
who writes in again: they may have left a marketing list while still expecting an answer to the
message they actually sent, and reversing a stated wish on the strength of one email is worse than
making staff aware of it. Inbound is still recorded and still visible to staff.
"""

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Channel, VisitorSession

logger = logging.getLogger("fussion.email.unsubscribe")

#: 32 bytes of entropy, URL-safe. The endpoint is unauthenticated, so this is the only thing
#: standing between "a guest asked to stop" and "anyone can stop anyone".
TOKEN_BYTES = 32


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


async def ensure_token(db: AsyncSession, session: VisitorSession) -> str:
    """Return this session's unsubscribe token, minting and persisting one if absent.

    Minted lazily rather than at session creation because only email uses it: a WhatsApp or widget
    session would otherwise carry a random string that has no meaning on its channel.
    """
    if session.unsubscribe_token:
        return session.unsubscribe_token
    token = new_token()
    session.unsubscribe_token = token
    await db.flush()
    return token


def unsubscribe_url(token: str) -> str:
    """The HTTPS URL a mail client will POST to, per RFC 8058.

    Absolute and https, both required: Gmail ignores a ``mailto:``-only header for one-click
    purposes. Built from ``effective_public_api_url`` rather than a request, because the URL is
    generated when a reply is composed but is fetched by the recipient's client seconds later, from
    a different network entirely.
    """
    from app.core.config import settings

    return f"{settings.effective_public_api_url.rstrip('/')}/api/v1/webhooks/email/unsubscribe/{token}"


async def apply_one_click(db: AsyncSession, token: str) -> bool:
    """Honour a one-click unsubscribe. Returns True when a live session was changed.

    Idempotent: clicking twice is not an error, which is what lets the endpoint answer 200
    unconditionally. Scoped to email sessions, because a token could in principle be replayed
    against another channel and a WhatsApp guest has no email consent to withdraw.
    """
    session = (
        await db.execute(
            select(VisitorSession).where(
                VisitorSession.unsubscribe_token == token,
                VisitorSession.channel == Channel.EMAIL,
            )
        )
    ).scalar_one_or_none()

    if session is None:
        # Unknown or already-purged token. Logged at info, not warned: an unauthenticated endpoint
        # will be probed, and a warning per probe trains people to ignore warnings.
        logger.info("email: unsubscribe token did not match a session")
        return False

    if session.unsubscribed_at is not None:
        logger.info("email: session %s was already unsubscribed", session.id)
        return False

    session.unsubscribed_at = datetime.now(UTC)
    await db.commit()
    logger.info(
        "email: session %s unsubscribed by one-click (guest %s)", session.id, session.external_id
    )
    return True


async def is_unsubscribed(db: AsyncSession, session: VisitorSession) -> bool:
    """Whether automated sends to this guest are suppressed."""
    return session.unsubscribed_at is not None


__all__ = [
    "TOKEN_BYTES",
    "apply_one_click",
    "ensure_token",
    "is_unsubscribed",
    "new_token",
    "unsubscribe_url",
]