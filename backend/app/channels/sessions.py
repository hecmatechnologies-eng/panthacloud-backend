"""Get-or-create a conversation session for a channel (ADR-004).

This is the first code to read the ``uq_visitor_session_channel_identity`` index, which 0033 created
and nothing used. Every decision here is forced by that index existing.

**Expiry revives; it does not replace.** One identity gets one session row, ever - the unique index
says so. So a guest who messages on Monday and again on Friday keeps the *same* session and the
same transcript, and the TTL is extended rather than a second row being written (which the
constraint would refuse anyway). That is the right behaviour for a phone number: it is the same
person, and splitting their thread in two is worse than a stale rate-limit window.

The TTL is therefore a *rate-limit* window, not a conversation boundary. Conversation retention is
the separate ``Conversation.retention_expires_at``, which is exactly why that field is its own
timestamp rather than being read off the session.

**A concurrent insert is an expected outcome, not an error.** Two deliveries of the same first
message arrive at once - a provider retry on a slow response - and both find nothing, so both
insert. The loser recovers the winner's row inside a savepoint rather than failing the webhook, so
the provider's retry is answered instead of being retried again.

That recovery only works if the unique index actually fires, and for two releases after it was
created it did not: ``thread_id`` was NULL for every conversation with no thread, and NULLs are
distinct inside a unique index on both engines, so the constraint admitted an unbounded number of
them. This module is what exposed it (migration 0035 and ``_thread_key`` fix it), which is the
argument for having written the first consumer of an index before building more on top of it.

**A channel session with no external id is refused.** It would be a row that looks like a channel
session, is excluded from the channel index by the partial predicate, and can therefore never be
looked up again - indistinguishable from the widget rows it is supposed to differ from.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel, ChannelIdentity
from app.core.config import settings
from app.models.conversation import VisitorSession


class ChannelSessionError(Exception):
    """A channel session was requested in a shape that cannot be stored or found again."""


@dataclass(frozen=True, slots=True)
class ChannelSession:
    session: VisitorSession
    #: True when this call inserted the row. False when an existing one was reused, including when
    #: a concurrent insert won the race.
    created: bool


def _ttl() -> timedelta:
    return timedelta(hours=settings.PUBLIC_SESSION_TTL_HOURS)


def _expires_at() -> datetime:
    return datetime.now(UTC) + _ttl()


def _thread_key(identity: ChannelIdentity) -> str:
    """The stored form of "no thread": ``''`` rather than NULL.

    NULL is a perfectly good answer to "is there a thread?" and a disastrous one to "what is the
    thread?", because NULLs are distinct inside a unique index - so rows differing only by that
    NULL all pass the constraint. Canonicalising to '' keeps the column readable and gives the key a
    value the index can refuse duplicates on. The index coalesces too, so this is the readable
    convention rather than the thing holding the guarantee up; see migration 0035.
    """
    return identity.key()[2] or ""


async def _find(
    db: AsyncSession, project_id: uuid.UUID, identity: ChannelIdentity
) -> VisitorSession | None:
    channel, external_id, _ = identity.key()
    # Coalesced on the read side as well as the index side, for two reasons: it matches rows
    # written before the canonical form, and it matches the indexed expression exactly, so the
    # planner can still use the index rather than scanning.
    return (
        await db.execute(
            select(VisitorSession).where(
                VisitorSession.project_id == project_id,
                VisitorSession.channel == channel,
                VisitorSession.external_id == external_id,
                func.coalesce(VisitorSession.thread_id, "") == _thread_key(identity),
            )
        )
    ).scalar_one_or_none()


def _as_utc(value: datetime) -> datetime:
    """Re-attach UTC to a naive datetime read back from the database.

    SQLite has no timezone-aware storage and hands back naive values; Postgres returns aware ones.
    Comparing the two directly raises TypeError, so a code path that is correct on production fails
    every time it runs against the test database - which is the arrangement where you least want to
    discover it. Normalising at the boundary is the fix; the alternative, a dialect check at every
    comparison site, is a bug waiting for the next site someone adds.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _revive(session: VisitorSession) -> VisitorSession:
    """Extend the TTL, and only when it has actually lapsed.

    Rewriting ``expires_at`` on every turn would make it a "last seen" column wearing a TTL's name,
    which is a different thing and would make the rate-limit window wrong.
    """
    if session.expires_at is None:
        return session
    if _as_utc(session.expires_at) <= datetime.now(UTC):
        session.expires_at = _expires_at()
    return session


async def get_or_create_session(
    db: AsyncSession, *, project_id: uuid.UUID, identity: ChannelIdentity
) -> ChannelSession:
    """Find this identity's session, or create it. Idempotent under concurrent delivery."""
    if identity.channel is Channel.WEB:
        raise ChannelSessionError(
            "the widget has its own session path; it is keyed by a client-supplied id and origin, "
            "not by an external identity"
        )
    if not identity.key()[1]:
        raise ChannelSessionError(
            "a channel session needs an external id; without one the row is excluded from the "
            "channel index and can never be found again"
        )

    existing = await _find(db, project_id, identity)
    if existing is not None:
        _revive(existing)
        await db.flush()
        return ChannelSession(session=existing, created=False)

    session = VisitorSession(
        project_id=project_id,
        # integration_id stays NULL: there is no widget behind a channel conversation, and
        # provenance is nullable precisely so that is expressible.
        integration_id=None,
        channel=identity.channel,
        external_id=identity.key()[1],
        thread_id=_thread_key(identity),
        origin=None,
        expires_at=_expires_at(),
    )

    # Savepoint, not the outer transaction. A bare rollback on IntegrityError would discard
    # whatever else the request had done before this point; the savepoint rolls back only the insert
    # that lost the race and leaves the request alive to answer the provider.
    try:
        async with db.begin_nested():
            db.add(session)
            await db.flush()
    except IntegrityError:
        winner = await _find(db, project_id, identity)
        if winner is None:  # pragma: no cover - the constraint fired, so a row must exist
            raise ChannelSessionError(
                "insert conflicted but no session was found; the constraint is firing for another "
                "reason than a duplicate identity"
            ) from None
        return ChannelSession(session=winner, created=False)

    return ChannelSession(session=session, created=True)