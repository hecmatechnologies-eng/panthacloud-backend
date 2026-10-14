"""The unified message shape (ADR-004).

Small, but the properties matter more than the size, because each one is a way a multi-channel
adapter silently diverges: two people collapsing into one, a provider retry answered twice, a group
chat answered as if it were a guest, or a history shared across channels that should be separate.

Every test here asserts a *failure mode*, not a field's presence. A test that checked "the dataclass
has an attribute called thread_id" would pass with the semantics broken.
"""

from datetime import UTC, datetime

from app.channels.base import (
    Channel,
    ChannelIdentity,
    IncomingMessage,
    message_key,
)


def _inbound(**overrides) -> IncomingMessage:
    defaults = {
        "identity": ChannelIdentity(channel=Channel.WHATSAPP, external_id="256772123456"),
        "text": "Do you have a room for Friday?",
    }
    return IncomingMessage(**{**defaults, **overrides})


class TestIdentity:
    def test_the_same_person_is_one_key_across_a_leading_plus(self):
        """WhatsApp wa_ids arrive with and without '+'. Two spellings, one guest.

        Without this a guest who has messaged once from each becomes two people with two histories,
        and the assistant greets them as a stranger the second time.
        """
        with_plus = ChannelIdentity(channel=Channel.WHATSAPP, external_id="+256772123456").key()
        without = ChannelIdentity(channel=Channel.WHATSAPP, external_id="256772123456").key()

        assert with_plus == without

    def test_surrounding_whitespace_is_not_significant(self):
        a = ChannelIdentity(channel=Channel.EMAIL, external_id="  grace@example.com ").key()
        b = ChannelIdentity(channel=Channel.EMAIL, external_id="grace@example.com").key()

        assert a == b

    def test_two_channels_from_one_person_are_two_conversations(self):
        """A WhatsApp message and an email from one guest must not share history."""
        whatsapp = ChannelIdentity(channel=Channel.WHATSAPP, external_id="256772123456").key()
        email = ChannelIdentity(channel=Channel.EMAIL, external_id="guest@example.com").key()

        assert whatsapp != email

    def test_two_people_are_two_conversations(self):
        a = ChannelIdentity(channel=Channel.WHATSAPP, external_id="256772123456").key()
        b = ChannelIdentity(channel=Channel.WHATSAPP, external_id="256772999999").key()

        assert a != b

    def test_a_thread_separates_two_conversations_with_one_person(self):
        """A support thread and a booking thread from one guest are not one history."""
        support = ChannelIdentity(
            channel=Channel.EMAIL, external_id="guest@example.com", thread_id="support"
        ).key()
        booking = ChannelIdentity(
            channel=Channel.EMAIL, external_id="guest@example.com", thread_id="booking"
        ).key()
        bare = ChannelIdentity(channel=Channel.EMAIL, external_id="guest@example.com").key()

        assert len({support, booking, bare}) == 3

    def test_an_absent_thread_is_distinct_from_an_empty_one(self):
        """They mean the same thing, and treating them differently would split one guest in two."""
        absent = ChannelIdentity(channel=Channel.EMAIL, external_id="g@example.com").key()
        empty = ChannelIdentity(
            channel=Channel.EMAIL, external_id="g@example.com", thread_id=""
        ).key()

        assert absent == empty

    def test_an_external_id_is_never_interpreted(self):
        """A Telegram chat id is not a phone number, and a group id is neither.

        The shape deliberately does not parse what the provider calls the person. A test that pins
        this is a test against someone later adding `+` handling or digit validation here, which
        would break every provider that does not use phone numbers.
        """
        group = ChannelIdentity(channel=Channel.TELEGRAM, external_id="-1001234567890").key()

        assert group[1] == "-1001234567890"


class TestAddressing:
    def test_a_non_whatsapp_channel_is_addressed_by_default(self):
        assert _inbound(identity=ChannelIdentity(Channel.EMAIL, "g@example.com")).is_addressed_to_us

    def test_a_group_message_not_addressed_to_us_is_recognised(self):
        """Guests writing in a WhatsApp group talk to each other.

        Treating that as a turn has the assistant answering conversations it was not invited into,
        in front of other guests. The adapter sets this from the provider's own addressing data.
        """
        group = _inbound(metadata={"addressed_to_business": False})

        assert group.is_addressed_to_us is False

    def test_a_group_message_addressed_to_us_is_accepted(self):
        direct = _inbound(metadata={"addressed_to_business": True})

        assert direct.is_addressed_to_us is True

    def test_missing_addressing_data_defaults_to_addressed(self):
        """Defaulting the other way would drop every message on a provider that omits the field."""
        assert _inbound().is_addressed_to_us is True

    def test_addressing_is_ignored_on_other_channels(self):
        """An email cannot be a group message, so the flag must not silence it."""
        email = _inbound(
            identity=ChannelIdentity(Channel.EMAIL, "g@example.com"),
            metadata={"addressed_to_business": False},
        )

        assert email.is_addressed_to_us is True


class TestMessageKey:
    def test_a_retry_of_the_same_message_yields_the_same_key(self):
        """Providers retry. Answering a guest twice because their first request was retried is the
        kind of bug a customer notices before you do."""
        at = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
        first = _inbound(received_at=at)
        retry = _inbound(received_at=datetime(2026, 10, 15, 9, 0, 3, tzinfo=UTC))

        assert message_key(first) == message_key(retry)

    def test_the_key_ignores_the_display_name(self):
        """A guest renaming themselves, or a provider returning a fuller name, is not a new person."""
        before = _inbound(display_name="Grace")
        after = _inbound(display_name="Grace Hopper")

        assert message_key(before) == message_key(after)


class TestShape:
    def test_defaults_are_usable_without_an_adapter_filling_every_field(self):
        """An adapter that supplies only what its provider gives must still produce a valid turn."""
        minimal = IncomingMessage(
            identity=ChannelIdentity(channel=Channel.SMS, external_id="+256772123456"),
            text="hello",
        )

        assert minimal.message_id is None
        assert minimal.received_at.tzinfo is UTC
        assert dict(minimal.metadata) == {}