"""The staff conversation inbox (ADR-004, K6).

Two reads: a cursor-paginated list across the organisation, and one conversation's transcript.
Nothing else - no writes, because approving a drafted reply needs outbound delivery that does not
exist yet, and an approval endpoint with nowhere to send would be theatre.

**Org-scoped, project-tenanted.** The route is organisation-level because that is where the side
nav entry lives and a group operator wants one inbox across all their properties. Every row still
carries its ``project_id``, and the tenant check is organisation membership - so the moment project
scoping arrives (deferred; the decision is written up in docs/TODO-KHOTELS-EVOLUTION.md) this becomes
a filter on the same query rather than a rewrite.

**Ordering is by conversation creation, not by most recent activity, and that is a known gap.** A
desk wants an old thread with a fresh reply at the top, which needs ordering by the newest message.
Doing that properly is one of two things, and both are worse than the imprecision:

- a denormalised ``last_message_at`` on the conversation, maintained by the runtime - where a single
  missed update silently misorders the inbox, and nothing would notice; or
- a correlated subquery for the newest message, repeated identically in both the ORDER BY *and* the
  cursor predicate - where the two drifting apart is a silent pagination bug that serves rows twice
  and skips others.

Neither is worth building before anyone has used the list. ``last_message_at`` is still *returned*,
so the frontend can surface the time; it just does not sort by it. Recorded rather than silently
shipped as if it were right.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.api.v1.endpoints._pagination import (
    InvalidCursor,
    cursor_http_error,
    decode_cursor,
    encode_cursor,
    next_link,
    parse_timestamp,
)
from app.channels.base import Channel
from app.core.permissions import Permission
from app.models.conversation import (
    Conversation,
    ConversationIntent,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
    VisitorSession,
)
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.project import Project
from app.schemas.conversation import (
    ConversationCounts,
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
)

router = APIRouter(prefix="/organizations/{org_id}", tags=["Conversations"])


@dataclass(frozen=True, slots=True)
class _PageStats:
    """What the logs table shows about a conversation's messages, for one page of conversations."""

    message_count: int
    last_message_at: object | None
    #: When the guest was first acknowledged. The prototype counts the assistant's *holding*
    #: reply here, so this is simply the first outbound message.
    first_reply_at: object | None
    #: When something actually reached the guest that was worth reading.
    #:
    #: Defined as the first outbound message that was **sent**, which is what makes it different
    #: from ``first_reply_at``: a drafted quote awaiting approval has not reached anybody, and
    #: counting it would report a useful answer for a price the guest has not seen. This is the
    #: prototype's "full answer or approved price in front of the guest".
    useful_answer_at: object | None
    #: When the guest first wrote. The logs table's "received", and the denominator for both.
    first_inbound_at: object | None


async def _message_stats(
    db: AsyncSession, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, _PageStats]:
    """Message aggregates for one page of conversations.

    A second query rather than an aggregate over the join, and deliberately: grouping every message
    in the organisation to then throw all but a page away costs more the more the product is used,
    which is precisely when the inbox is most likely to be open. Keyset narrows the conversation
    set first, so this only ever touches the page.
    """
    if not conversation_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Message.conversation_id,
                func.count(Message.id),
                func.max(Message.created_at),
                func.min(Message.created_at).filter(
                    Message.direction == MessageDirection.OUTBOUND
                ),
                func.min(Message.created_at).filter(
                    Message.direction == MessageDirection.OUTBOUND,
                    Message.status == MessageStatus.SENT,
                ),
                func.min(Message.created_at).filter(
                    Message.direction == MessageDirection.INBOUND
                ),
            )
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        )
    ).all()
    return {
        row[0]: _PageStats(
            message_count=row[1],
            last_message_at=row[2],
            first_reply_at=row[3],
            useful_answer_at=row[4],
            first_inbound_at=row[5],
        )
        for row in rows
    }


def _timing_fields(stats: _PageStats | None) -> dict[str, object]:
    """The three timings, or nulls throughout when the conversation has no messages.

    Shared by the list and the detail so the guest card opened from a row cannot disagree with
    that row. Two definitions of "useful answer" would eventually drift, and the drift would only
    show as a panel that disagrees with the row above it.
    """
    s = stats or _PageStats(0, None, None, None, None)
    return {
        "first_reply_at": s.first_reply_at,
        "useful_answer_at": s.useful_answer_at,
        "first_inbound_at": s.first_inbound_at,
    }


def _stats_fields(stats: _PageStats | None) -> dict[str, object]:
    """Timings plus the counts the list shows."""
    s = stats or _PageStats(0, None, None, None, None)
    return {
        **_timing_fields(s),
        "message_count": s.message_count,
        "last_message_at": s.last_message_at,
    }


@router.get(
    "/conversations/counts",
    response_model=ConversationCounts,
    summary="How many conversations are waiting on each desk",
)
# Declared before `/conversations/{conversation_id}` and it must stay that way: FastAPI matches in
# registration order and the two paths have the same segment count, so reversing them would make
# `counts` parse as a conversation id and answer 422 instead of 200.
async def conversation_counts(
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CONVERSATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationCounts:
    """Counts for the three inbox tabs.

    A separate endpoint rather than a ``total`` on the list, because the list is paginated and a
    count derived from the rows on screen would be a lie: the desk sees 25 of 4,000 and the badge
    would say 25. These are real aggregates over the whole tenant.

    The groups partition the way the reference's tabs do:

    - ``logs`` is everything, so it is the total rather than a filtered count.
    - ``approvals`` is ``AWAITING_APPROVAL`` alone - one state, because a rejected draft stays there.
    - ``followups`` is ``AWAITING_GUEST`` (a quote is out, waiting on the guest) plus ``LOST``.
      ``BOOKED`` is excluded deliberately: the guest converted and there is nothing to chase.

    Follow-up *scheduling* is not counted. ``next_follow_up_at`` is a schedule rather than a status
    and a conversation can hold one in any state, so counting it would need a second aggregate -
    and the tab is defined by status, so the badge has to match what the tab will actually list.
    """
    org, _ = tenant

    rows = (
        await db.execute(
            select(Conversation.status, func.count(Conversation.id))
            .join(VisitorSession, VisitorSession.id == Conversation.session_id)
            .join(Project, Project.id == VisitorSession.project_id)
            .where(Project.organization_id == org.id)
            .group_by(Conversation.status)
        )
    ).all()
    by_status = {status: count for status, count in rows}

    return ConversationCounts(
        logs=sum(by_status.values()),
        approvals=by_status.get(ConversationStatus.AWAITING_APPROVAL, 0),
        followups=by_status.get(ConversationStatus.AWAITING_GUEST, 0)
        + by_status.get(ConversationStatus.LOST, 0),
    )


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    summary="List conversations across the organization",
)
async def list_conversations(
    request: Request,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CONVERSATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    status_filter: Annotated[list[ConversationStatus] | None, Query(alias="status")] = None,
    intent: Annotated[list[ConversationIntent] | None, Query()] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    channel: Annotated[list[Channel] | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> list[ConversationSummary]:
    """Guest session logs, newest conversation first.

    Bare JSON array with an RFC 8288 ``Link`` header for the next page, matching every other
    collection here - see ``_pagination`` for why the response body does not move.
    """
    org, _ = tenant

    # Conversation has no project_id: the anchor lives on VisitorSession, one row per session.
    # Joining is the honest way to filter by tenancy rather than copying the column down and
    # creating two that can disagree.
    stmt = (
        select(Conversation, VisitorSession, Project.name)
        .join(VisitorSession, VisitorSession.id == Conversation.session_id)
        .join(Project, Project.id == VisitorSession.project_id)
        .where(Project.organization_id == org.id)
    )

    if status_filter:
        stmt = stmt.where(Conversation.status.in_(status_filter))
    if intent:
        stmt = stmt.where(Conversation.intent.in_(intent))
    if project_id:
        stmt = stmt.where(VisitorSession.project_id == project_id)
    if channel:
        stmt = stmt.where(VisitorSession.channel.in_(channel))

    if cursor:
        # Keyset on the same (created_at, id) DESC ordering below, so a conversation created
        # mid-pagination does not shift the window and cause a row to be served twice or missed.
        try:
            state = decode_cursor(cursor)
            stmt = stmt.where(
                tuple_(Conversation.created_at, Conversation.id)
                < tuple_(parse_timestamp(state["created_at"]), uuid.UUID(state["id"]))
            )
        except (InvalidCursor, KeyError, ValueError):
            raise cursor_http_error() from None

    order = (Conversation.created_at.desc(), Conversation.id.desc())

    if limit is None:
        rows = (await db.execute(stmt.order_by(*order))).all()
    else:
        # limit + 1: the extra row is how we know another page exists without a COUNT.
        fetched = (await db.execute(stmt.order_by(*order).limit(limit + 1))).all()
        has_more = len(fetched) > limit
        rows = fetched[:limit]
        if has_more:
            last_conversation = rows[-1][0]
            response.headers["Link"] = next_link(
                request_path=request.url.path,
                params={
                    "status": status_filter,
                    "intent": intent,
                    "project_id": project_id,
                    "channel": channel,
                },
                limit=limit,
                cursor=encode_cursor(
                    {
                        "created_at": last_conversation.created_at,
                        "id": str(last_conversation.id),
                    }
                ),
            )

    stats = await _message_stats(db, [row[0].id for row in rows])

    return [
        ConversationSummary(
            id=conversation.id,
            session_id=session.id,
            project_id=session.project_id,
            project_name=project_name,
            channel=session.channel,
            external_id=session.external_id,
            status=conversation.status,
            intent=conversation.intent,
            value=conversation.value,
            lost_reason=conversation.lost_reason,
            next_follow_up_at=conversation.next_follow_up_at,
            **_stats_fields(stats.get(conversation.id)),
            created_at=conversation.created_at,
        )
        for conversation, session, project_name in rows
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Retrieve one conversation and its transcript",
)
async def get_conversation(
    request: Request,
    tenant: Annotated[
        tuple[Organization, Membership],
        Depends(require_permission(Permission.CONVERSATION_VIEW)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    conversation_id: uuid.UUID,
) -> ConversationDetail:
    """The message exchange for one conversation.

    Scoped to the caller's organisation the same way the list is: a conversation belonging to
    another tenant's project is not found rather than refused, so the id cannot be probed for
    existence.
    """
    org, _ = tenant
    row = (
        await db.execute(
            select(Conversation, VisitorSession, Project.name)
            .join(VisitorSession, VisitorSession.id == Conversation.session_id)
            .join(Project, Project.id == VisitorSession.project_id)
            .where(Conversation.id == conversation_id, Project.organization_id == org.id)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    conversation, session, project_name = row
    # Same aggregates as the list, from the same function, so the guest card opened from a row
    # cannot disagree with that row. Two definitions of "useful answer" would eventually drift.
    stats = (await _message_stats(db, [conversation.id])).get(conversation.id)
    # created_at alone is not a total order - two messages can land in the same tick - so role is
    # the tiebreak. It is deterministic, which is what a transcript needs to be.
    messages = list(
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc(), Message.role.asc())
            )
        )
        .scalars()
        .all()
    )

    return ConversationDetail(
        id=conversation.id,
        session_id=session.id,
        project_id=session.project_id,
        project_name=project_name,
        channel=session.channel,
        external_id=session.external_id,
        status=conversation.status,
        intent=conversation.intent,
        value=conversation.value,
        lost_reason=conversation.lost_reason,
        next_follow_up_at=conversation.next_follow_up_at,
        created_at=conversation.created_at,
        **_timing_fields(stats),
        messages=[ConversationMessage.model_validate(m) for m in messages],
    )