"""Resolving a messaging address to a tenant (ADR-004).

The table is the channel counterpart to ``allowed_origals``, and this is the question a webhook
arrives asking: a WhatsApp delivery carries a ``wa_id`` and nothing else identifying.

The tests that matter most are the boring ones - a number registered with a '+' and the same number
arriving without one, an address that is not registered, a registration that has been retired. The
failure mode is not a crash; it is a guest's message being answered by the wrong hotel's assistant,
which is exactly the bug this table exists to make impossible.

The refusal is deliberately the same exception as the widget path's, so "no such number" and "that
number is someone else's" are indistinguishable from outside - there is a test for that too.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel, normalize_external_id
from app.models.channel_registration import ChannelRegistration
from app.runtime.resolver import TenantResolutionError, channel_context, resolve_channel_tenant

NUMBER = "256772123456"


async def make_project(client: AsyncClient) -> tuple[str, str]:
    """A registered user, org and project. Returns ``(organization_id, project_id)``."""
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"resolve-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"Resolve {suffix}",
            "org_name": f"Resolve Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    proj = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": "Hotel", "slug": f"resolve-{suffix}"},
    )
    assert proj.status_code == 201, proj.text
    return org_id, proj.json()["id"]


@pytest.fixture
async def project_id(client: AsyncClient) -> tuple[str, str]:
    """One project. For tests needing a *second*, call ``make_project`` directly - a fixture is
    cached per test, so asking for it twice would hand back the same project and quietly test
    nothing about two tenants."""
    return await make_project(client)


async def claim(db: AsyncSession, owner: tuple[str, str], **kwargs) -> ChannelRegistration:
    """Register an address for a project, stored in canonical form as the application would.

    ``raw`` is the address as the tenant typed it; ``channel`` defaults to WhatsApp.
    """
    org_id, proj_id = owner
    channel = kwargs.pop("channel", Channel.WHATSAPP)
    raw = kwargs.pop("raw", NUMBER)
    row = ChannelRegistration(
        organization_id=uuid.UUID(org_id),
        project_id=uuid.UUID(proj_id),
        channel=channel,
        external_identifier=normalize_external_id(channel, raw),
        **kwargs,
    )
    db.add(row)
    await db.commit()
    return row


# ============================================================
# Resolution
# ============================================================


class TestResolution:
    async def test_a_claimed_address_resolves_to_its_project(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        await claim(db_session, project_id)

        ctx = await resolve_channel_tenant(
            db_session, channel=Channel.WHATSAPP, external_id=NUMBER
        )

        assert ctx.project_id == uuid.UUID(project_id[1])
        assert ctx.organization_id == uuid.UUID(project_id[0])
        assert ctx.integration_id is None
        assert ctx.origin is None

    async def test_the_result_is_usable_as_a_turn_source(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """Resolution is only worth anything if what it returns can actually run a turn."""
        await claim(db_session, project_id)
        ctx = await resolve_channel_tenant(
            db_session, channel=Channel.WHATSAPP, external_id=NUMBER
        )

        assert ctx == channel_context(
            organization_id=uuid.UUID(project_id[0]), project_id=uuid.UUID(project_id[1])
        )

    @pytest.mark.parametrize("registered", ["+256772123456", "256772123456", " 256772123456 "])
    @pytest.mark.parametrize("arriving", ["256772123456", "+256772123456"])
    async def test_the_plus_is_a_spelling_difference_not_a_different_number(
        self,
        db_session: AsyncSession,
        project_id: tuple[str, str],
        registered: str,
        arriving: str,
    ) -> None:
        """Every combination must land on the one row.

        WhatsApp wa_ids arrive without the '+' while the number a hotel prints on its signage has
        one, so this is the normal path rather than an edge case. Two hand-written normalisers would
        eventually differ by a character and split a guest's history in two.
        """
        await claim(db_session, project_id, raw=registered)

        ctx = await resolve_channel_tenant(
            db_session, channel=Channel.WHATSAPP, external_id=arriving
        )

        assert ctx.project_id == uuid.UUID(project_id[1])

    async def test_telegram_and_sms_resolve_their_own_addresses(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """One address per channel: the same digits claimed on two channels are two registrations."""
        await claim(db_session, project_id, channel=Channel.WHATSAPP, raw=NUMBER)
        await claim(db_session, project_id, channel=Channel.TELEGRAM, raw="998877")

        wa = await resolve_channel_tenant(
            db_session, channel=Channel.WHATSAPP, external_id=NUMBER
        )
        tg = await resolve_channel_tenant(
            db_session, channel=Channel.TELEGRAM, external_id="998877"
        )

        assert wa.project_id == tg.project_id == uuid.UUID(project_id[1])

        with pytest.raises(TenantResolutionError):
            await resolve_channel_tenant(
                db_session, channel=Channel.TELEGRAM, external_id=NUMBER
            )


class TestRefusals:
    async def test_an_unclaimed_address_is_refused(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        await claim(db_session, project_id, raw=NUMBER)

        with pytest.raises(TenantResolutionError):
            await resolve_channel_tenant(
                db_session, channel=Channel.WHATSAPP, external_id="256700000000"
            )

    async def test_an_empty_address_is_refused(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """Not left to find nothing by accident. The caller learns nothing either way, but the
        refusal is a decision rather than a query that happened to miss."""
        await claim(db_session, project_id)

        for blank in ("", "   ", "++"):
            with pytest.raises(TenantResolutionError):
                await resolve_channel_tenant(
                    db_session, channel=Channel.WHATSAPP, external_id=blank
                )

    async def test_a_retired_registration_answers_nothing(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """Deactivating is how a number is let go without giving it away.

        It still holds the address - that is the point - so the row stays and the tenant simply
        stops hearing from that number.
        """
        await claim(db_session, project_id, is_active=False)

        with pytest.raises(TenantResolutionError):
            await resolve_channel_tenant(
                db_session, channel=Channel.WHATSAPP, external_id=NUMBER
            )

    async def test_the_web_channel_is_refused_here(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """The widget resolves by public key and Origin. Routing it here too would be a second,
        weaker path to the same tenancy."""
        await claim(db_session, project_id, channel=Channel.WEB, raw="pk_live_123")

        with pytest.raises(TenantResolutionError):
            await resolve_channel_tenant(
                db_session, channel=Channel.WEB, external_id="pk_live_123"
            )

    async def test_email_is_refused_rather_than_half_supported(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """Email routing is genuinely different and is not written.

        An inbound email is addressed to a routing address the tenant controls, but a *reply* comes
        from whatever address the guest typed, which matches no registration. Answering on the To:
        header alone would silently drop every guest who replies from a different address - so this
        refuses until that design exists, rather than appearing to work for the first message of a
        thread and then going quiet.
        """
        await claim(db_session, project_id, channel=Channel.EMAIL, raw="guest-desk@hotel.com")

        with pytest.raises(TenantResolutionError):
            await resolve_channel_tenant(
                db_session, channel=Channel.EMAIL, external_id="guest-desk@hotel.com"
            )

    async def test_every_refusal_says_the_same_thing(
        self, db_session: AsyncSession, project_id: tuple[str, str]
    ) -> None:
        """The webhook must not be an oracle for which numbers are registered.

        A different message for "no such number" than for "that number is retired" tells whoever is
        asking which numbers belong to a named tenant, which is a directory of every hotel's
        contact details. Every refusal here is the same one, byte for byte, including the one for
        a channel that cannot be routed at all.
        """
        await claim(db_session, project_id, raw=NUMBER, is_active=False)

        messages = {
            "unknown number": await _refusal(db_session, Channel.WHATSAPP, "256700000000"),
            "retired number": await _refusal(db_session, Channel.WHATSAPP, NUMBER),
            "blank address": await _refusal(db_session, Channel.WHATSAPP, ""),
            "unroutable channel": await _refusal(db_session, Channel.EMAIL, "a@b.com"),
        }

        assert len(set(messages.values())) == 1, (
            f"the refusals distinguish the cases, so a caller can probe: {messages}"
        )


async def _refusal(db: AsyncSession, channel: Channel, external_id: str) -> str:
    """The message a caller would see for one refusal."""
    try:
        await resolve_channel_tenant(db, channel=channel, external_id=external_id)
    except TenantResolutionError as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


class TestOneAddressOneProject:
    async def test_two_projects_cannot_claim_one_number(
        self, db_session: AsyncSession, project_id: tuple[str, str], client: AsyncClient
    ) -> None:
        """The constraint that answers the open question, enforced by the database.

        A shared number has no way to decide which project an unknown guest wanted, so allowing it
        would mean refusing first contact or routing on something else. Making that a constraint
        rather than a convention is what stops it being quietly relaxed later.
        """
        org_a, proj_a = project_id
        org_b, proj_b = await make_project(client)
        assert proj_a != proj_b

        await claim(db_session, (org_a, proj_a), raw=NUMBER)

        db_session.add(
            ChannelRegistration(
                organization_id=uuid.UUID(org_b),
                project_id=uuid.UUID(proj_b),
                channel=Channel.WHATSAPP,
                external_identifier=NUMBER,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_a_retired_registration_still_holds_its_number(
        self, db_session: AsyncSession, project_id: tuple[str, str], client: AsyncClient
    ) -> None:
        """Uniqueness spans is_active on purpose.

        If it did not, a number retired by hotel A could be registered to hotel B, and then
        reactivated on A - putting A's historical conversations in front of hotel B's assistant.
        """
        org_a, proj_a = project_id
        org_b, proj_b = await make_project(client)
        assert proj_a != proj_b

        await claim(db_session, (org_a, proj_a), raw=NUMBER, is_active=False)

        db_session.add(
            ChannelRegistration(
                organization_id=uuid.UUID(org_b),
                project_id=uuid.UUID(proj_b),
                channel=Channel.WHATSAPP,
                external_identifier=NUMBER,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()


class TestNormalisation:
    def test_a_leading_plus_is_dropped_for_addressable_channels(self) -> None:
        assert normalize_external_id(Channel.WHATSAPP, "+256772123456") == "256772123456"
        assert normalize_external_id(Channel.SMS, "  +256772123456 ") == "256772123456"

    def test_an_email_is_folded_because_providers_fold_it(self) -> None:
        """The local part is case-sensitive by the letter of RFC 5321 and case-insensitive in every
        provider in practice, so folding is what matches the guest's experience."""
        assert normalize_external_id(Channel.EMAIL, "Guest@Example.COM") == "guest@example.com"

    def test_a_handle_is_left_alone(self) -> None:
        """A Telegram username starts with '@' and has no country code; nothing to strip."""
        assert normalize_external_id(Channel.TELEGRAM, "@hotel_desk") == "@hotel_desk"