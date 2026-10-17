"""Seed a clearly-labelled demo organisation so the overview charts have something to draw.

**Why this exists.** The dashboard refuses to chart below 20 answered conversations, which is the
right behaviour and means a brand-new installation shows an empty page. That is correct for a
tenant and useless for checking that the charts render at all. This script builds a *separate*
organisation for that purpose. It never touches the hotel's own organisation, because the whole point
of the metrics is that they describe one real tenant.

**Rerunnable.** Running it twice wipes and rebuilds only this demo org's conversations, matched by
the organisation slug below. It will not duplicate, and it will not touch any other tenant.

Usage, from ``backend/``::

    python scripts/seed_demo_overview.py
"""

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import delete, select

from app.core.database import get_session_factory
from app.core.security import hash_password
from app.models.conversation import (
    Channel,
    Conversation,
    ConversationIntent,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageRole,
    VisitorSession,
)
from app.models.membership import Membership, RoleEnum
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User

# Deliberately distinctive. Anyone who stumbles into this tenant, including in a screenshot, should
# be able to tell at a glance that the numbers are generated.
DEMO_ORG_SLUG = "k-hotels-sample-data"
DEMO_EMAIL = "sample-data@example.com"
DEMO_PASSWORD = "Password123!"

DAYS_OF_HISTORY = 84

# Weighted the way a small hotel actually gets traffic. Web widget first because most enquiries
# start on the hotel's own site; email second because that is how the existing bookings arrive;
# the rest present but small. All five are seeded so the channel chart shows a real split rather
# than three bars and two empty slots.
CHANNEL_WEIGHTS = {
    Channel.WEB: 0.34,
    Channel.EMAIL: 0.41,
    Channel.WHATSAPP: 0.17,
    Channel.TELEGRAM: 0.05,
    Channel.SMS: 0.03,
}

# Questions a guest actually asks a hotel, so the stored content is not filler.
QUESTIONS = [
    "What time is check-out?",
    "Is breakfast included in the room rate?",
    "Can I check in early? I land at 9am.",
    "Does the room have air conditioning?",
    "Is there a gym, and is it open all day?",
    "How far is the airport from you?",
    "Can I leave my bags with you after check-out?",
    "Is there parking at the hotel?",
    "What is the wifi password?",
    "Can I book a taxi to the city centre?",
]
ANSWERS = [
    "Check-out is by 11:00.",
    "Yes, breakfast is included.",
    "Early check-in depends on availability — I have noted your request.",
    "Every room is air conditioned.",
    "The gym is open from 6am to 11pm.",
    "About 25 minutes by taxi.",
    "Of course, we can hold your bags.",
    "There is free parking on site.",
    "The password is on your key card.",
    "I can arrange a taxi for you.",
]


#: First and last names for sample guests. Nothing here is a real person, and every address lands
#: on `example.com` - the domain RFC 2606 reserves for documentation precisely so that a demo can
#: never send mail to somebody who happens to share a name with a generated guest.
GIVEN_NAMES = [
    "Amara", "Brian", "Chloe", "Daniel", "Esther", "Farouk", "Grace", "Hakim",
    "Ibrahim", "Joy", "Kelvin", "Lydia", "Moses", "Nadia", "Oscar", "Priya",
]
FAMILY_NAMES = [
    "Adeyemi", "Bako", "Chukwu", "Dlamini", "Ekor", "Fumba", "Girma", "Hakim",
    "Ibrahim", "Juma", "Kato", "Lukwesa", "Mutesi", "Nakato", "Okello", "Ssali",
]

#: Uganda's country code and mobile prefix, **without a leading plus**.
#:
#: The convention in this codebase is that `external_id` holds a bare identifier and the display
#: layer formats it for the channel - `guestContact()` prepends "+" itself for phone channels. A
#: seeder that writes "+2567..." therefore renders "++256700000980", which is how the first run of
#: this fix was caught. Sample data has to obey the same contract as real data.
UGANDA_MOBILE_PREFIX = "2567"


def _contact_for(channel: Channel, rng: random.Random, ordinal: int) -> str | None:
    """A plausible contact for the channel the guest arrived on.

    ``None`` means "no identifier", which is the honest value for the website widget: a guest who
    typed on the hotel's page has not told us who they are, and inventing an address for them makes
    the row say something untrue. It renders as "Widget visitor".

    ``ordinal`` is mixed into every generated value rather than left to chance. Sampling names
    without it collides: sixteen by sixteen names is 256 addresses, and a thousand sessions need a
    thousand, so the run dies partway through on the unique index that stops one guest appearing
    twice. Real addresses carry trailing digits for the same reason.

    The previous version stamped a UUID into every session regardless of channel, which put strings
    like ``013fdfd673524cafb96c0f2c8bf73dab`` in the guest column - and because the formatter
    prefixes anything that is not email or telegram with "+", a widget guest rendered as
    ``+013fdfd673524cafb96c0f2c8bf73dab``. A UUID wearing a phone number.
    """
    if channel == Channel.EMAIL:
        given = rng.choice(GIVEN_NAMES).lower()
        family = rng.choice(FAMILY_NAMES).lower()
        return f"{given}.{family}.{ordinal}@example.com"
    if channel == Channel.TELEGRAM:
        # The formatter strips the leading "-" and prepends "@", so this expects a negative integer
        # chat id - the same shape real Telegram ids take.
        return f"-{1_000_000_000 + ordinal}"
    if channel in (Channel.WHATSAPP, Channel.SMS):
        return f"{UGANDA_MOBILE_PREFIX}{ordinal:08d}"
    return None


def _wait_seconds(day_index: int, total_days: int, rng: random.Random) -> int:
    """A plausible improvement curve, not a straight line.

    Answer time falls over the window - that is the thing the dashboard exists to show - but it
    falls with noise and it plateaus rather than reaching zero, because a real deployment never
    answers instantly. Anyone reading these numbers should see a shape worth arguing about.
    """
    progress = day_index / max(1, total_days - 1)
    # 5 hours down to roughly 10 minutes, eased so the early drop is fast and the tail is flat.
    target_minutes = 300 * (1 - progress) ** 2.2 + 8
    # Log-normal-ish jitter: most replies near the target, a few much slower.
    jitter = rng.lognormvariate(0, 0.55)
    return max(45, int(target_minutes * jitter * 60))


async def main() -> None:
    rng = random.Random(20261017)  # Fixed, so a reseed produces the same curve.
    session_factory = get_session_factory()
    async with session_factory() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
            )
        ).scalar_one_or_none()

        if org is not None:
            # Rebuild only this org. Conversations are reached through project -> session, so the
            # deletes have to be explicit; there is no cascade configured for them.
            project_ids = list(
                (
                    await session.execute(
                        select(Project.id).where(Project.organization_id == org.id)
                    )
                ).scalars()
            )
            if project_ids:
                session_ids = list(
                    (
                        await session.execute(
                            select(VisitorSession.id).where(
                                VisitorSession.project_id.in_(project_ids)
                            )
                        )
                    ).scalars()
                )
                if session_ids:
                    conversation_ids = list(
                        (
                            await session.execute(
                                select(Conversation.id).where(
                                    Conversation.session_id.in_(session_ids)
                                )
                            )
                        ).scalars()
                    )
                    if conversation_ids:
                        await session.execute(
                            delete(Message).where(Message.conversation_id.in_(conversation_ids))
                        )
                        await session.execute(
                            delete(Conversation).where(Conversation.id.in_(conversation_ids))
                        )
                        await session.execute(
                            delete(VisitorSession).where(VisitorSession.id.in_(session_ids))
                        )
            print(f"cleared existing sample data for {DEMO_ORG_SLUG}")

        if org is None:
            org = Organization(name="K Hotels (sample data)", slug=DEMO_ORG_SLUG)
            session.add(org)
            await session.flush()

            user = User(
                email=DEMO_EMAIL,
                hashed_password=hash_password(DEMO_PASSWORD),
                full_name="Sample Data",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            session.add(
                Membership(
                    user_id=user.id,
                    organization_id=org.id,
                    role=RoleEnum.OWNER,
                )
            )
            print(f"created organisation {org.slug} ({DEMO_EMAIL} / {DEMO_PASSWORD})")

        project = (
            await session.execute(
                select(Project).where(
                    Project.organization_id == org.id, Project.slug == "k-hotels"
                )
            )
        ).scalar_one_or_none()
        if project is None:
            project = Project(
                organization_id=org.id,
                name="K Hotels",
                slug="k-hotels",
                description="Sample data for the overview charts. Not a real property.",
            )
            session.add(project)
        await session.flush()

        # Backdate the project so "days since launch" is measured from the start of the history
        # rather than from today. A project created now with 84 days of history would claim to have
        # been answering guests since launch in a way that contradicts its own creation date.
        project.created_at = datetime.now(UTC) - timedelta(days=DAYS_OF_HISTORY + 1)
        await session.flush()

        now = datetime.now(UTC)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        created = 0

        for day_index in range(DAYS_OF_HISTORY):
            day = today - timedelta(days=DAYS_OF_HISTORY - 1 - day_index)
            is_weekend = day.weekday() >= 5
            # Weekends are busier, and the assistant handles them slightly slower.
            volume = rng.randint(14, 20) if is_weekend else rng.randint(7, 12)

            for _ in range(volume):
                asked_at = day + timedelta(
                    hours=rng.randint(7, 22), minutes=rng.randint(0, 59)
                )
                if asked_at > now:
                    asked_at = now - timedelta(minutes=rng.randint(5, 90))

                # `created_at` set explicitly. Left to default it becomes the moment this script ran,
                # which put 945 sessions on a single day and made a per-day channel chart useless -
                # one spike, nothing else. The session is the thing that happened on the day.
                channel = rng.choices(
                    list(CHANNEL_WEIGHTS), weights=list(CHANNEL_WEIGHTS.values()), k=1
                )[0]
                visitor = VisitorSession(
                    project_id=project.id,
                    channel=channel,
                    external_id=_contact_for(channel, rng, created),
                    created_at=asked_at,
                    expires_at=asked_at + timedelta(days=30),
                )
                session.add(visitor)
                await session.flush()

                # Roughly one in fifteen is something a human should look at.
                serious = rng.random() < 0.065
                status = (
                    ConversationStatus.ESCALATED if serious and rng.random() < 0.5
                    else ConversationStatus.ANSWERED
                )
                intent = (
                    ConversationIntent.COMPLAINT if serious else ConversationIntent.INFORMATIONAL
                )
                # A small share of genuine enquiries never got answered. They must stay in the data
                # so the charts show a real gap rather than a suspiciously perfect line.
                answered = rng.random() > 0.04

                conversation = Conversation(
                    session_id=visitor.id,
                    status=status,
                    intent=intent,
                    created_at=asked_at,
                    retention_expires_at=asked_at + timedelta(days=365),
                )
                session.add(conversation)
                await session.flush()

                session.add(
                    Message(
                        conversation_id=conversation.id,
                        role=MessageRole.VISITOR,
                        direction=MessageDirection.INBOUND,
                        content=rng.choice(QUESTIONS),
                        created_at=asked_at,
                    )
                )
                if answered:
                    wait = _wait_seconds(day_index, DAYS_OF_HISTORY, rng)
                    session.add(
                        Message(
                            conversation_id=conversation.id,
                            role=MessageRole.ASSISTANT,
                            direction=MessageDirection.OUTBOUND,
                            content=rng.choice(ANSWERS),
                            created_at=asked_at + timedelta(seconds=wait),
                        )
                    )
                created += 1

        await session.commit()
        print(f"seeded {created} conversations across {DAYS_OF_HISTORY} days")


if __name__ == "__main__":
    asyncio.run(main())