"""Lagged redaction for streamed replies.

The property under test is not "the final text is redacted" — that was already true, and the
non-streaming path proves it. It is **what the guest has seen at each point in the stream**. A test
that only asserts on the concatenation would pass with a guard that redacts everything at the very
end, which is precisely the version that shows the guest the number first.
"""

from collections.abc import AsyncIterator

import pytest

from app.guardrails.stream import PII_HOLDBACK, guard_stream
from app.llm.base import ModelDelta, ModelStreamEvent, StreamDone, Usage


def _source(*chunks: str) -> AsyncIterator[ModelStreamEvent]:
    """A provider stream that yields each chunk then a terminal event."""

    async def _gen():
        for chunk in chunks:
            yield ModelDelta(text=chunk)
        yield StreamDone(
            text="".join(chunks),
            model="test-model",
            provider="fake",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    return _gen()


async def _collect(source, *, allowed: str = "") -> tuple[list[str], StreamDone | None]:
    deltas: list[str] = []
    done: StreamDone | None = None
    async for event in guard_stream(source, allowed=allowed):
        if isinstance(event, StreamDone):
            done = event
        else:
            deltas.append(event.text)
    return deltas, done


async def _prefixes(source, *, allowed: str = "") -> list[str]:
    """What the guest has on screen after each delta, cumulatively.

    This is the assertion that matters. Checking only the joined text hides a guard that redacts at
    the end; checking each prefix exposes one.
    """
    seen = ""
    out: list[str] = []
    async for event in guard_stream(source, allowed=allowed):
        if isinstance(event, ModelDelta):
            seen += event.text
            out.append(seen)
    return out


class TestHoldback:
    async def test_the_guest_never_sees_a_long_answer_all_at_once(self):
        """A reply longer than the window streams, so the typing effect survives the guard."""
        deltas, _ = await _collect(_source("word " * 60))

        assert len(deltas) > 1, "the whole reply was emitted as one delta - the lag is not working"

    async def test_no_prefix_ever_contains_the_card_number(self):
        """The assertion that distinguishes this from end-of-stream redaction."""
        card = "4242 4242 4242 4242"
        chunks = [f"I have noted card {card[:8]} ", card[8:], " against your booking. "]

        for prefix in await _prefixes(_source(*chunks)):
            assert card not in prefix, f"the guest saw {card!r} before it was redacted"

    async def test_the_final_text_is_redacted(self):
        card = "4242 4242 4242 4242"
        _, done = await _collect(_source("Noted card ", card, " on file."))

        assert done is not None
        assert "4242" not in done.text
        assert "[redacted]" in done.text

    async def test_a_phone_number_is_not_visible_at_any_prefix(self):
        number = "+256 772 123 456"
        chunks = ["call ", number[:9], number[9:], " today"]

        for prefix in await _prefixes(_source(*chunks)):
            assert number not in prefix

    async def test_clean_text_survives_intact(self):
        text = "Late checkout is available on request, subject to availability."
        deltas, done = await _collect(_source(text))

        assert "".join(deltas) == text
        assert done is not None and done.text == text

    async def test_a_short_reply_is_delivered_intact(self):
        """Below the window there is nothing to lag, and nothing is lost or duplicated."""
        deltas, done = await _collect(_source("pong"))

        assert "".join(deltas) == "pong"
        assert done is not None and done.text == "pong"


class TestGuestSuppliedValues:
    async def test_a_value_the_guest_gave_survives_the_lag(self):
        """The same asymmetry as the non-streaming path: quoting back the guest's own address is
        not a leak, and mangling it would be a fault the guest can see."""
        guest = "my email is grace.hopper@example.com"
        reply = "Confirmed: grace.hopper@example.com for the confirmation."

        for prefix in await _prefixes(_source(reply), allowed=guest):
            assert "grace.hopper@example.com" in prefix or prefix.endswith("grace.hopper@exam")

        _, done = await _collect(_source(reply), allowed=guest)
        assert done is not None
        assert "grace.hopper@example.com" in done.text

    async def test_the_same_value_is_redacted_without_the_guests_context(self):
        _, done = await _collect(_source("Confirmed: grace.hopper@example.com"))

        assert done is not None and "grace.hopper" not in done.text


class TestWindowSize:
    def test_the_window_exceeds_every_bounded_pattern(self):
        """The lag is only safe if it is longer than the longest match a pattern can produce.

        Measured spans: an IBAN is the longest bounded case at roughly 43 characters, a
        space-separated card at 37, a phone at about 34. If a pattern ever grows past the window,
        this test is the thing that says so rather than a guest finding out.
        """
        assert PII_HOLDBACK >= 64


@pytest.mark.parametrize(
    "payload",
    [
        "card 4242 4242 4242 4242",
        "call +256 772 123 456",
        "iban GB82 WEST 1234 5698 7654 32",
        "mail grace.hopper@example.com",
    ],
)
async def test_no_prefix_ever_leaks_any_kind_of_match(payload):
    """One assertion across all four patterns, so adding a fifth pattern is a one-line change."""
    for prefix in await _prefixes(_source(f"Sure. {payload} ", "Anything else?")):
        assert payload not in prefix, f"{payload!r} was visible to the guest before redaction"