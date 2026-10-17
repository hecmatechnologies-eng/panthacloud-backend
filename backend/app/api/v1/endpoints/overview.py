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

#: Canonical order for the channel series.
#:
#: Fixed rather than alphabetical or by volume on purpose. The chart assigns a colour by position in
#: this list, and the database returns grouped rows in whatever order the planner likes - so any
#: order derived from the result would let a channel change colour between two page loads, and the
#: reader would have to re-learn the chart. Anything not listed is appended, sorted, so a channel
#: added to the platform later still gets a stable slot.
CHANNEL_ORDER = ("web", "whatsapp", "email", "telegram", "sms")

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


class ChannelDay(BaseModel):
    """One day's guest sessions, split by where the conversation started.

    Keyed per channel rather than as a fixed set of columns, because the available channels are a
    platform-wide decision and a tenant may only use some of them. Hardcoding three would make the
    other two silently vanish from a hotel that does use them - which is how the weekly series ended
    up reporting a hardcoded zero for messages.
    """

    date: str
    #: Channel value -> session count. Absent channels are omitted rather than sent as zero.
    sessions: dict[str, int]


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
    #: Sessions per day by channel. Deliberately outside ``insufficient_data``: traffic is traffic,
    #: and a hotel can know where its guests arrive long before there are enough answered
    #: conversations to say anything about how quickly they were answered.
    channel_daily: list[ChannelDay] = Field(default_factory=list)
    #: Every channel seen in the window, so the chart can label the series without guessing.
    channels: list[str] = Field(default_factory=list)


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
    goal_minutes: int = DEFAULT_GOAL_MINUTES,
) -> OverviewMetrics:
    projects = await _require_org_projects(db, org_id)
    project_ids = [p.id for p in projects]

    launched_at = min((p.created_at for p in projects), default=None)
    days = max(1, min(days, 90))
    # Clamped rather than validated. A hotel aiming at 15 minutes is normal; 0 or negative is a
    # typo, and every day would then trivially "meet" the goal. The upper bound is generous enough
    # that nobody hits it in anger.
    goal_minutes = max(1, min(goal_minutes, 24 * 60))
    # Anchored to midnight and counting today as one of the days, so "the last 14 days" is 14
    # calendar dates and not 15. Measuring back 14*24 hours from the current instant spans both
    # endpoints inclusively, which produced 15 points under a caption saying 14 - a chart with one
    # more day on it than the sentence promised.
    now = datetime.now(UTC)
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=days - 1
    )

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

    # Named `wait_pairs`, not `waits`: a plain list of per-day minutes is also called `waits` below,
    # and a subquery shadowed by a list fails at the `.c` with an error that names neither.
    wait_pairs = _wait_seconds_expr().subquery()
    daily_waits = (
        await db.execute(
            select(
                func.date(wait_pairs.c.asked_at).label("d"),
                func.avg(
                    extract("epoch", wait_pairs.c.answered_at) - extract("epoch", wait_pairs.c.asked_at)
                ).label("wait"),
            )
            .where(
                wait_pairs.c.conversation_id.in_(conversation_ids),
                wait_pairs.c.asked_at >= window_start,
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
    # Against `goal_minutes`, not the module constant. The goal is a query parameter, and scoring the
    # days against a hard-coded 12 while reporting a different goal would put a number on the page
    # that no setting on the page can reproduce.
    days_met = sum(1 for w in waits if w <= goal_minutes)

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

    buckets: dict[str, dict[str, float]] = {}
    for row in conversation_days:
        d = _as_date(row[0])
        monday = (d - timedelta(days=d.weekday())).isoformat()
        bucket = buckets.setdefault(
            monday,
            {"conversations": 0, "serious": 0, "wait_seconds": 0.0, "waited_count": 0.0},
        )
        bucket["conversations"] += row[1]
        bucket["serious"] += row[2] or 0

    # Message volume and wait time over the same window as the conversation counts. Queried per day
    # and summed in Python, because grouping a week in SQL needs date_trunc and SQLite does not
    # have it. Day-level rows are enough to rebuild an exact weekly figure as long as what is
    # summed is additive - hence a sum of seconds and a count, never a mean of means.
    weekly_start = datetime.now(UTC) - timedelta(weeks=WEEKLY_WEEKS)

    weekly_messages = (
        await db.execute(
            select(
                func.date(Message.created_at).label("d"),
                func.count(Message.id).label("messages"),
            )
            .where(
                Message.conversation_id.in_(conversation_ids),
                Message.role == MessageRole.VISITOR,
                Message.direction == MessageDirection.INBOUND,
                Message.created_at >= weekly_start,
            )
            .group_by("d")
        )
    ).all()

    weekly_wait_seconds = (
        await db.execute(
            select(
                func.date(wait_pairs.c.asked_at).label("d"),
                func.sum(
                    extract("epoch", wait_pairs.c.answered_at) - extract("epoch", wait_pairs.c.asked_at)
                ).label("seconds"),
                func.count(wait_pairs.c.conversation_id).label("n"),
            )
            .where(
                wait_pairs.c.conversation_id.in_(conversation_ids),
                wait_pairs.c.asked_at >= weekly_start,
            )
            .group_by("d")
        )
    ).all()

    for row in weekly_messages:
        d = _as_date(row[0])
        monday = (d - timedelta(days=d.weekday())).isoformat()
        bucket = buckets.setdefault(
            monday,
            {"conversations": 0, "serious": 0, "wait_seconds": 0.0, "waited_count": 0.0},
        )
        bucket["messages"] = bucket.get("messages", 0) + row[1]

    for row in weekly_wait_seconds:
        d = _as_date(row[0])
        monday = (d - timedelta(days=d.weekday())).isoformat()
        bucket = buckets.setdefault(
            monday,
            {"conversations": 0, "serious": 0, "wait_seconds": 0.0, "waited_count": 0.0},
        )
        bucket["wait_seconds"] += float(row[1] or 0)
        bucket["waited_count"] += float(row[2] or 0)

    weekly: list[WeeklyPoint] = []
    for week_start, bucket in sorted(buckets.items()):
        count = int(bucket["conversations"])
        serious = bucket["serious"]
        waited = bucket["waited_count"]
        # Mean over conversations, not over days. A mean of daily means would let a Tuesday with
        # three enquiries count as much as a Saturday with twenty, which is the one weighting a
        # "how long did guests wait" figure must not have.
        mean_weekly = (bucket["wait_seconds"] / waited / 60) if waited else None
        weekly.append(
            WeeklyPoint(
                week_start=week_start,
                guest_messages=int(bucket.get("messages", 0)),
                answered_conversations=count,
                average_wait_minutes=_rounded(mean_weekly),
                serious_per_100=_rounded(serious / count * 100) if count else None,
            )
        )

    # --- channels: where guests arrive -------------------------------------------------------
    # Sessions, not conversations. A session is one guest arriving; a conversation is what happened
    # after. "Where do our guests come from" is a question about arrivals, and a guest who opened a
    # widget and never wrote anything is still a guest who arrived.
    channel_rows = (
        await db.execute(
            select(
                func.date(VisitorSession.created_at).label("d"),
                VisitorSession.channel,
                func.count(VisitorSession.id).label("n"),
            )
            .where(
                VisitorSession.project_id.in_(project_ids),
                VisitorSession.created_at >= window_start,
            )
            .group_by("d", VisitorSession.channel)
            .order_by("d")
        )
    ).all()

    channel_daily: list[ChannelDay] = []
    channels_seen: list[str] = []
    per_day: dict[str, dict[str, int]] = {}
    for row in channel_rows:
        day = _as_date(row[0]).isoformat()
        # Enum member to its stored value, so the API speaks "email" and not "Channel.EMAIL".
        channel = getattr(row[1], "value", row[1])
        per_day.setdefault(day, {})[str(channel)] = int(row[2])
        if str(channel) not in channels_seen:
            channels_seen.append(str(channel))

    # One point per day in the window, not just the days that had traffic. A missing day in the
    # middle of a series is read by a chart as "no change" rather than "nothing happened".
    day_cursor = (window_start).date()
    last_day = datetime.now(UTC).date()
    while day_cursor <= last_day:
        key = day_cursor.isoformat()
        channel_daily.append(ChannelDay(date=key, sessions=per_day.get(key, {})))
        day_cursor += timedelta(days=1)

    # Canonical order, so the colour a channel is given does not depend on the query plan. Unlisted
    # channels sort after the known ones, alphabetically, and keep a stable slot of their own.
    channels_seen.sort(
        key=lambda c: (
            CHANNEL_ORDER.index(c) if c in CHANNEL_ORDER else len(CHANNEL_ORDER),
            c,
        )
    )

    return OverviewMetrics(
        goal_minutes=goal_minutes,
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
        channel_daily=channel_daily,
        channels=channels_seen,
    )


__all__ = ["router"]