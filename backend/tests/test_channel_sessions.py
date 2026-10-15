"""Channel session resolution (ADR-004).

Every test here is a failure mode that a naive implementation gets wrong and that is invisible in
review. The important ones:

- **Expiry revives rather than replaces.** A guest who messages on Monday and again on Friday must
  not be split into two threads, and the unique index makes "replace" impossible anyway.
- **A concurrent insert recovers instead of raising.** Two deliveries of one first message is the
  normal case for a provider retry, and a webhook that 500s is a webhook the provider retries
  forever.
- **A leading '+' is one person.** WhatsApp wa_ids arrive both ways.
- **A channel session with no external id is refused**, not quietly written as a row that can never
  be found again.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.channels.base import Channel, ChannelIdentity
from app.channels.sessions import (
    ChannelSessionError,
    get_or_create_session,
)
from app.core.database import get_session_factory
from app.models.conversation import VisitorSession


@pytest.fixture
async def project_id(client) -> str:
    """A real project, because the session's FK must be satisfiable.

    Created over HTTP rather than by constructing ORM rows: the point of these tests is session
    resolution, and hand-building a user/organization/project asserts whatever fields I guessed
    were required rather than what they are.
    """
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"chan-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"Chan {suffix}",
            "org_name": f"Chan Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    orgs = await client.get("/api/v1/organizations", headers=headers)
    org_id = orgs.json()[0]["id"]

    proj = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": "Chan", "slug": f"p-{suffix}"},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


def _wa(number: str = "256772123456") -> ChannelIdentity:
    return ChannelIdentity(channel=Channel.WHATSAPP, external_id=number)


def _immediate(value):
    """Return ``value`` without awaiting - the stub `_find` is a plain lambda."""

    async def _retrieved(*args, **kwargs):
        return value

    return _retrieved()


class TestCreate:
    async def test_a_first_message_creates_a_session(self, db_session, project_id):
        result = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )

        assert result.created is True
        assert result.session.channel is Channel.WHATSAPP
        assert result.session.integration_id is None, "a channel conversation has no widget behind it"
        assert result.session.origin is None

    async def test_the_next_message_reuses_it(self, db_session, project_id):
        first = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )
        second = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )

        assert second.created is False
        assert second.session.id == first.session.id

    async def test_the_row_is_findable_after_the_request_ends(self, db_session, project_id):
        """The index is only worth having if a later request can find the row with it."""
        await get_or_create_session(db_session, project_id=uuid.UUID(project_id), identity=_wa())
        await db_session.commit()

        async with get_session_factory()() as fresh:
            found = (
                await fresh.execute(
                    select(VisitorSession).where(
                        VisitorSession.project_id == uuid.UUID(project_id),
                        VisitorSession.external_id == "256772123456",
                    )
                )
            ).scalar_one()

        assert found.channel is Channel.WHATSAPP


class TestIdentity:
    async def test_a_leading_plus_is_the_same_guest(self, db_session, project_id):
        """WhatsApp wa_ids arrive both ways; two spellings must not become two guests."""
        await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa("+256772123456")
        )
        again = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa("256772123456")
        )

        assert again.created is False

    async def test_two_channels_are_two_sessions(self, db_session, project_id):
        whatsapp = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )
        email = await get_or_create_session(
            db_session,
            project_id=uuid.UUID(project_id),
            identity=ChannelIdentity(channel=Channel.EMAIL, external_id="guest@example.com"),
        )

        assert whatsapp.session.id != email.session.id

    async def test_a_thread_is_a_separate_conversation_with_one_person(self, db_session, project_id):
        support = ChannelIdentity(
            channel=Channel.EMAIL, external_id="g@example.com", thread_id="support"
        )
        booking = ChannelIdentity(
            channel=Channel.EMAIL, external_id="g@example.com", thread_id="booking"
        )

        a = await get_or_create_session(db_session, project_id=uuid.UUID(project_id), identity=support)
        b = await get_or_create_session(db_session, project_id=uuid.UUID(project_id), identity=booking)

        assert a.session.id != b.session.id

    async def test_a_naive_expiry_from_sqlite_is_compared_correctly(
        self, db_session, project_id
    ):
        """SQLite returns naive datetimes and Postgres returns aware ones.

        Comparing a value read back from either against ``datetime.now(UTC)`` raises TypeError on
        the naive side. That failure mode is invisible in production and certain in CI, which is
        the arrangement where it is least welcome.
        """
        first = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )
        naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        first.session.expires_at = naive
        await db_session.flush()

        revived = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )

        assert revived.session.expires_at.tzinfo is not None
        assert revived.session.expires_at > datetime.now(UTC)


class TestExpiry:
    async def test_an_expired_session_is_revived_not_replaced(self, db_session, project_id):
        """The same guest coming back next week keeps their transcript.

        The unique index forbids a second row for this identity, so 'replace' was never an option -
        but the behaviour has to be stated deliberately, because a session TTL that silently
        starts a new transcript is a bug a guest would describe as 'it forgot me'.
        """
        first = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )
        original_id = first.session.id
        original_expiry = first.session.expires_at

        first.session.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.flush()

        revived = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )

        assert revived.created is False
        assert revived.session.id == original_id
        assert revived.session.expires_at > original_expiry

    async def test_a_live_session_is_not_rewritten(self, db_session, project_id):
        """Rewriting expires_at every turn would make it 'last seen' wearing a TTL's name, and the
        rate-limit window would be wrong."""
        first = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )
        before = first.session.expires_at

        await get_or_create_session(db_session, project_id=uuid.UUID(project_id), identity=_wa())

        assert first.session.expires_at == before


class TestRefusals:
    async def test_a_channel_session_with_no_external_id_is_refused(self, db_session, project_id):
        """Writing it would create a row excluded from the channel index by the partial predicate -
        unfindable for ever, and indistinguishable from a widget row."""
        with pytest.raises(ChannelSessionError, match="external id"):
            await get_or_create_session(
                db_session,
                project_id=uuid.UUID(project_id),
                identity=ChannelIdentity(channel=Channel.WHATSAPP, external_id="   "),
            )

    async def test_the_widget_is_refused_rather_than_double_handled(self, db_session, project_id):
        """The widget is keyed by a client-supplied id and origin. Routing it here would create a
        second, parallel session path for the only channel that already has one."""
        with pytest.raises(ChannelSessionError, match="widget"):
            await get_or_create_session(
                db_session,
                project_id=uuid.UUID(project_id),
                identity=ChannelIdentity(channel=Channel.WEB, external_id="whatever"),
            )


class TestConcurrency:
    async def test_a_conflicting_insert_recovers_the_winner(
        self, db_session, project_id, monkeypatch
    ):
        """The behaviour that actually matters, proven without depending on engine locking.

        Two deliveries of one first message both SELECT, both miss, both INSERT. The loser must
        return the winner's row rather than raising, because a webhook that 500s is a webhook the
        provider retries again.

        ``_find`` is stubbed to miss so the conflict is produced deterministically. Racing two real
        transactions does not work as a test here, and the reason matters: SQLite has no predicate
        locking, so a unique index does not fire for a row another *uncommitted* transaction is
        inserting - both inserts succeed and neither is refused. Postgres does block and raise
        UniqueViolation, which is the behaviour the savepoint exists to absorb. So the race was
        verified live on Postgres, and the recovery is verified here.
        """
        pid = uuid.UUID(project_id)
        identity = _wa()

        winner = await get_or_create_session(db_session, project_id=pid, identity=identity)
        await db_session.commit()

        # The row exists and is committed; this call must nonetheless behave as if it had missed.
        monkeypatch.setattr(
            "app.channels.sessions._find",
            lambda *a, **k: _immediate(winner.session),
        )

        result = await get_or_create_session(db_session, project_id=pid, identity=identity)

        assert result.created is False
        assert result.session.id == winner.session.id

    async def test_the_constraint_refuses_a_second_row_for_one_identity(
        self, db_session, project_id
    ):
        """The mechanism the recovery above depends on, provoked directly.

        The duplicate is written with ``thread_id = None`` on purpose, because that is the case the
        index used to get wrong. NULLs are distinct inside a unique index on both engines, so
        before migration 0035 this insert was accepted: three rows with thread_id of NULL, '' and
        'x' coexisted without complaint, and the guarantee this module is built on silently did not
        hold for the most common kind of conversation there is - one with no thread.

        Racing two real transactions cannot test this on SQLite, and the reason is worth recording
        rather than working around quietly: SQLite has no predicate locking, so a unique index does
        *not* fire for a row that another still-uncommitted transaction is inserting - both inserts
        succeed and neither is refused. Postgres does block and raise UniqueViolation, which is
        precisely what the savepoint absorbs. So the real race was verified live against Postgres,
        and the constraint itself is pinned down here, where it is deterministic.
        """
        pid = uuid.UUID(project_id)
        first = await get_or_create_session(db_session, project_id=pid, identity=_wa())
        await db_session.commit()

        duplicate = VisitorSession(
            project_id=pid,
            channel=Channel.WHATSAPP,
            external_id="256772123456",
            thread_id=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

        remaining = (
            await db_session.execute(
                select(VisitorSession).where(
                    VisitorSession.project_id == pid,
                    VisitorSession.external_id == "256772123456",
                )
            )
        ).scalars().all()
        assert [s.id for s in remaining] == [first.session.id]

    async def test_no_thread_is_stored_as_empty_not_null(
        self, db_session, project_id
    ):
        """The canonical form, asserted on the stored value.

        NULL answers "is there a thread?" honestly and answers "what is the thread?" not at all,
        which is how the index ended up not firing. Storing '' keeps the row readable to anyone
        reading the table, and keeps a writer who forgets the convention inside the constraint
        rather than outside it.
        """
        result = await get_or_create_session(
            db_session, project_id=uuid.UUID(project_id), identity=_wa()
        )

        assert result.session.thread_id == ""

    async def test_a_legacy_null_thread_row_is_still_found(
        self, db_session, project_id
    ):
        """Rows written before the canonical form must not become invisible.

        The lookup coalesces for exactly this: a row stored with NULL would otherwise be missed by
        a query that compares against '', and the caller would open a second session for a guest who
        already has one.
        """
        pid = uuid.UUID(project_id)
        legacy = VisitorSession(
            project_id=pid,
            channel=Channel.WHATSAPP,
            external_id="256772123456",
            thread_id=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(legacy)
        await db_session.commit()

        result = await get_or_create_session(db_session, project_id=pid, identity=_wa())

        assert result.created is False
        assert result.session.id == legacy.id