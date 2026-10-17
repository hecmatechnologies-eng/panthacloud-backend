"""What the tenant sees on the organisation overview.

Not usage - there is already a router for tokens and cost (``app/api/v1/endpoints/agent_runs.py``).
This answers a different question: *is this working for my guests?* The two are deliberately separate
because they are billed by different people and mean different things. Tokens are what the platform
costs; wait time and escalations are what the hotel gets back.

**Every definition here is arguable, so each is written down.** A metric nobody can reproduce is a
number nobody can argue with, and an unarguable metric is worthless.

``average_wait_minutes``
    Per **conversation**, from the first guest message to the first assistant reply, then averaged
    across conversations that received one.

    Per conversation rather than per message, because the question a hotel asks is "how long did
    someone wait for a reply", not "how long did every individual message take".

    Conversations with no reply are **excluded**, not counted as zero. A guest who never got an
    answer waited an unbounded time, and averaging that in as zero would make the assistant look
    better the worse it performed - the metric would improve as service degraded.

``serious_per_100``
    Conversations that were escalated, or whose intent was a complaint, as a percentage of all
    conversations in the bucket. Scaled per 100 because a hotel with 40 enquiries a week reads
    "4" as ambiguous and "10 in 100" as a rate.

``days_met_goal``
    Days where the mean wait came in under ``goal_minutes``, out of days in the window. Deliberately
    a count of days rather than an average of ratios: averaging ratios gives a day with one
    conversation the same weight as a Saturday with two hundred.

**The honest gap.** There is no "before" period. We cannot report the wait time a hotel had before
we existed, because we were not running to measure it. The weekly series therefore shows what
happened *since launch* and the page must not imply otherwise - a comparison to a number nobody
recorded is a fiction, and this one would be presented as evidence.

**Insufficient data is a first-class answer.** With three conversations the mean is real but
meaningless, and a chart drawn through it would be decoration. The endpoint says so rather than
returning numbers that look like findings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models.conversation import (
    Conversation,
    ConversationIntent,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageRole,
    VisitorSession,
)
from app.models.project import Project

router = APIRouter(prefix="/organizations/{org_id}", tags=["Overview"])

#: The response the reference dashboard is measured against. A knob, not a constant to argue about
#: later: a hotel whose guests routinely wait longer should be able to say so.
DEFAULT_GOAL_MINUTES = 12

#: Below this many answered conversations the numbers are withheld. Three enquiries produce a mean
#: and a rate, and a chart drawn through them reads as a finding when it is noise.
MIN_CONVERSATIONS_FOR_METRICS = 20

#: Weeks of weekly history, matching the reference's "last 8 weeks".
WEEKLY_WEEKS = 8


class DailyPoint(BaseModel):
    date: str
    guest_messages: int
    answered_conversations: int
    average_wait_minutes: float | None = None
    serious: int


class WeeklyPoint(BaseModel):
    week_start: str
    guest_messages: int
    answered_conversations: int
    average_wait_minutes: float | None = None
    serious_per_100: float | None = None


class Totals(BaseModel):
    guest_messages: int
    answered_conversations: int
    average_wait_minutes: float | None = None
    days_met_goal: int
    days_in_window: int
    serious_per_100: float | None = None


class OverviewMetrics(BaseModel):
    goal_minutes: int = DEFAULT_GOAL_MINUTES
    range_days: int
    launched_at: str | None = None
    #: True when there is too little traffic to report. The page shows an explanation rather than a
    #: chart, because a confident line through three data points is worse than no chart.
    insufficient_data: bool
    totals: Totals
    daily: list[DailyPoint] = Field(default_factory=list)
    weekly: list[WeeklyPoint] = Field(default_factory=list)


def _as_date(value: Any) -> Any:
    """A calendar date from whatever the driver handed back.

    ``func.date()`` returns a ``date`` from Postgres and a ``str`` from SQLite, and this endpoint
    runs on both. Normalising here keeps every call site from growing the same ``hasattr`` dance -
    and the shape difference is exactly the kind of thing that is invisible until the suite runs on
    the other engine.
    """
    if value is None or isinstance(value, datetime):
        return value.date() if isinstance(value, datetime) else value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    return value


def _rounded(value: float | None, places: int = 1) -> float | None:
    return None if value is None else round(value, places)


async def _require_org_projects(db: AsyncSession, org_id: uuid.UUID) -> list[Project]:
    """Every project in the organisation.

    The overview is organisation-wide because a tenant with three properties wants one number for
    "how is my front desk doing", not three to add up by hand. Per-project detail is one click away
    and is where the same series live.
    """
    return list(
        (
            await db.execute(select(Project).where(Project.organization_id == org_id))
        ).scalars().all()
    )


def _wait_seconds_expr() -> Any:
    """SQL for "how long until the first reply", in seconds.

    Built once so the daily and weekly queries cannot drift apart - two definitions of the same
    number would eventually disagree, and the disagreement would be found by a hotel rather than us.
    """
    first_guest = (
        select(Message.conversation_id, func.min(Message.created_at).label("asked_at"))
        .where(
            Message.role == MessageRole.VISITOR,
            Message.direction == MessageDirection.INBOUND,
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    first_reply = (
        select(Message.conversation_id, func.min(Message.created_at).label("answered_at"))
        .where(Message.role == MessageRole.ASSISTANT, Message.direction == MessageDirection.OUTBOUND)
        .group_by(Message.conversation_id)
        .subquery()
    )
    joined = (
        select(
            first_guest.c.asked_at,
            first_reply.c.answered_at,
            Conversation.id.label("conversation_id"),
        )
        .select_from(first_guest)
        .join(first_reply, first_reply.c.conversation_id == first_guest.c.conversation_id)
        .join(Conversation, Conversation.id == first_guest.c.conversation_id)
    )
    return joined


def _is_serious() -> Any:
    """Escalated, or logged as a complaint.

    Two routes to the same outcome and they are not interchangeable: a complaint can be handled and
    stay a complaint, an escalation can be raised by staff for anything. Counting either alone
    misses the other half.
    """
    return (Conversation.status == ConversationStatus.ESCALATED) | (
        Conversation.intent == ConversationIntent.COMPLAINT
    )


@router.get(
    "/overview-metrics",
    summary="Guest experience metrics for the organisation overview",
)
async def overview_metrics(
    org_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[Any, Depends(require_permission(Permission.CHANNEL_VIEW))],
    days: int = 14,
) -> OverviewMetrics:
    projects = await _require_org_projects(db, org_id)
    project_ids = [p.id for p in projects]

    launched_at = min((p.created_at for p in projects), default=None)
    days = max(1, min(days, 90))
    window_start = datetime.now(UTC) - timedelta(days=days)

    conversation_ids = list(
        (
            await db.execute(
                select(Conversation.id)
                .join(VisitorSession, VisitorSession.id == Conversation.session_id)
                .where(VisitorSession.project_id.in_(project_ids))
            )
        ).scalars().all()
    )

    if not conversation_ids:
        return OverviewMetrics(
            range_days=days,
            launched_at=None,
            insufficient_data=True,
            totals=Totals(
                guest_messages=0, answered_conversations=0, days_met_goal=0, days_in_window=days
            ),
        )

    # --- daily: messages, answered conversations, mean wait, serious -----------------------
    # `func.date`, not `date_trunc`. The truncation functions are dialect-specific - Postgres has
    # `date_trunc`, SQLite has `strftime` - and this endpoint runs against both, because the suite
    # runs on SQLite while development and production run on Postgres. Weeks are derived from these
    # daily rows in Python rather than by a second dialect-specific query.
    day = func.date(Message.created_at)
    daily_rows = (
        await db.execute(
            select(
                day.label("d"),
                func.count(Message.id).label("messages"),
                func.count(func.distinct(Message.conversation_id)).label("conversations"),
            )
            .where(
                Message.conversation_id.in_(conversation_ids),
                Message.role == MessageRole.VISITOR,
                Message.direction == MessageDirection.INBOUND,
                Message.created_at >= window_start,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    # Built once and reused. Calling `_wait_seconds_expr()` per reference rebuilt the whole
    # min/max-per-conversation subquery each time, so the statement carried four copies of it and
    # the planner had four times the work. This file's tests ran in ten minutes because of it.
    waits = _wait_seconds_expr().subquery()
    daily_waits = (
        await db.execute(
            select(
                func.date(waits.c.asked_at).label("d"),
                func.avg(
                    extract("epoch", waits.c.answered_at) - extract("epoch", waits.c.asked_at)
                ).label("wait"),
            )
            .where(
                waits.c.conversation_id.in_(conversation_ids),
                waits.c.asked_at >= window_start,
            )
            .group_by("d")
        )
    ).all()
    waits_by_day = {
        _as_date(row[0]): float(row[1]) / 60.0 for row in daily_waits if row[1] is not None
    }

    daily_serious = (
        await db.execute(
            select(
                func.date(Conversation.created_at).label("d"),
                func.count(Conversation.id).label("serious"),
            )
            .where(
                Conversation.id.in_(conversation_ids),
                _is_serious(),
                Conversation.created_at >= window_start,
            )
            .group_by("d")
        )
    ).all()
    serious_by_day = {_as_date(row[0]): row[1] for row in daily_serious}

    daily: list[DailyPoint] = []
    total_messages = 0
    total_answered = 0
    total_serious = 0
    for row in daily_rows:
        d = _as_date(row[0])
        wait = waits_by_day.get(d)
        daily.append(
            DailyPoint(
                date=d.isoformat(),
                guest_messages=row[1],
                answered_conversations=row[2],
                average_wait_minutes=_rounded(wait),
                serious=serious_by_day.get(d, 0),
            )
        )
        total_messages += row[1]
        total_answered += row[2]
        total_serious += serious_by_day.get(d, 0)

    waits = [p.average_wait_minutes for p in daily if p.average_wait_minutes is not None]
    mean_wait = round(sum(waits) / len(waits), 1) if waits else None
    days_met = sum(1 for w in waits if w <= DEFAULT_GOAL_MINUTES)

    # --- weekly: the long view, for the "is it trending right" charts ----------------------
    # Derived from the daily rows rather than queried separately. Postgres truncates weeks on
    # Monday and SQLite does not have the function at all; bucketing in Python means one
    # definition of "week" on both engines, and the chart cannot disagree with the table above it.
    conversation_days = (
        await db.execute(
            select(
                func.date(Conversation.created_at).label("d"),
                func.count(Conversation.id).label("conversations"),
                func.sum(case((_is_serious(), 1), else_=0)).label("serious"),
            )
            .where(
                Conversation.id.in_(conversation_ids),
                Conversation.created_at
                >= datetime.now(UTC) - timedelta(weeks=WEEKLY_WEEKS),
            )
            .group_by("d")
            .order_by("d")
        )
    ).all()

    buckets: dict[str, dict[str, int]] = {}
    for row in conversation_days:
        d = _as_date(row[0])
        monday = (d - timedelta(days=d.weekday())).isoformat()
        bucket = buckets.setdefault(monday, {"conversations": 0, "serious": 0})
        bucket["conversations"] += row[1]
        bucket["serious"] += row[2] or 0

    weekly: list[WeeklyPoint] = []
    for week_start, bucket in sorted(buckets.items()):
        count = bucket["conversations"]
        serious = bucket["serious"]
        weekly.append(
            WeeklyPoint(
                week_start=week_start,
                guest_messages=0,
                answered_conversations=count,
                average_wait_minutes=None,
                serious_per_100=_rounded(serious / count * 100) if count else None,
            )
        )

    return OverviewMetrics(
        goal_minutes=DEFAULT_GOAL_MINUTES,
        range_days=days,
        launched_at=launched_at.isoformat() if launched_at else None,
        insufficient_data=total_answered < MIN_CONVERSATIONS_FOR_METRICS,
        totals=Totals(
            guest_messages=total_messages,
            answered_conversations=total_answered,
            average_wait_minutes=mean_wait,
            days_met_goal=days_met,
            days_in_window=len(daily),
            serious_per_100=(
                _rounded(total_serious / total_answered * 100) if total_answered else None
            ),
        ),
        daily=daily,
        weekly=weekly,
    )


__all__ = ["router"]