"""PII guardrail: detection, masking, and the asymmetry between inbound and outbound.

The false-positive tests are the important half. On a hotel desk the text is full of short digit
runs that are not PII — room numbers, booking references, years, extension numbers — and a
guardrail that redacts those is worse than none, because the guest gets an answer with holes in it
and no indication why.

The outbound tests are the other half. "Redact everything" is the easy implementation and the wrong
one: the assistant is routinely asked to repeat back the contact details it was just given.
"""

from app.guardrails.pii import PIIKind, find_pii, redact, redact_outbound


def _kinds(text: str) -> list[PIIKind]:
    return [match.kind for match in find_pii(text)]


class TestDetection:
    def test_finds_an_email(self):
        matches = find_pii("please reply to grace.hopper@example.com about the booking")
        assert [m.kind for m in matches] == [PIIKind.EMAIL]
        assert matches[0].value == "grace.hopper@example.com"

    def test_finds_a_card_that_passes_luhn(self):
        # 4242 4242 4242 4242 - the canonical Luhn-valid test number.
        matches = find_pii("card 4242 4242 4242 4242 please")
        assert PIIKind.CARD in [m.kind for m in matches]

    def test_rejects_a_digit_run_that_fails_luhn(self):
        """Length alone must not be the test, or every long booking reference is a card."""
        assert PIIKind.CARD not in _kinds("reference 1234 5678 9012 3456")

    def test_finds_an_international_phone(self):
        assert PIIKind.PHONE in _kinds("call +256 772 123 456 this afternoon")

    def test_finds_an_iban(self):
        assert PIIKind.IBAN in _kinds("account GB82 WEST 1234 5698 7654 32")


class TestFalsePositives:
    """The cases that would make a hotel guest's answer come back with holes in it."""

    def test_a_bare_digit_run_is_not_a_phone(self):
        # Room number, booking reference, a year. Not PII.
        assert find_pii("room 101, booking BK-20394, arriving 2027") == []

    def test_a_separated_but_short_number_is_not_a_phone(self):
        """This is the case the length floor actually decides.

        The bare-digit tests above pass whatever the floor is, because a run with no separator
        never matches the phone pattern at all - they were free passes. A separated short number
        is the one that reaches the pattern and must be rejected on length, and hotel prose is full
        of them: suite numbers, split rates, "12-01" style references.
        """
        assert find_pii("suite 12-01, rate 50-40 per night") == []
        assert find_pii("press 9-3 for reception") == []

    def test_a_separated_number_long_enough_to_be_a_phone_is_one(self):
        """The other side of the same boundary, so the floor cannot be satisfied by disabling the
        pattern instead."""
        assert PIIKind.PHONE in _kinds("call 256-772-1234 now")

    def test_a_short_number_is_not_a_phone(self):
        assert find_pii("extension 4021") == []

    def test_prose_is_untouched(self):
        prose = (
            "The restaurant serves breakfast from 6am to 10am. Our pool closes at 8pm. "
            "Late checkout is available on request, subject to availability."
        )
        assert redact(prose) == prose

    def test_a_year_is_not_a_card(self):
        assert PIIKind.CARD not in _kinds("we opened in 1998 and renovated in 2024")


class TestOverlap:
    def test_a_longer_span_wins_over_a_shorter_one_inside_it(self):
        """An IBAN also matches the card and phone patterns; the caller must not see three
        overlapping spans and have to re-derive precedence at every call site."""
        iban = "GB82 WEST 1234 5698 7654 32"
        matches = find_pii(f"pay to {iban} today")

        assert len(matches) == 1, [m.kind for m in matches]
        assert matches[0].kind == PIIKind.IBAN


class TestRedaction:
    def test_redacts_and_preserves_the_rest(self):
        out = redact("Email grace@example.com to confirm.")
        assert out == "Email [redacted] to confirm."

    def test_redacts_every_occurrence(self):
        out = redact("a@b.com and c@d.org")
        assert out.count("[redacted]") == 2

    def test_clean_text_is_returned_unchanged(self):
        assert redact("no contact details here") == "no contact details here"


class TestOutboundAsymmetry:
    """The rule: redact what the model invented, keep what the guest supplied."""

    def test_a_number_the_model_invented_is_redacted(self):
        out = redact_outbound("I have noted your card 4242 4242 4242 4242 on file.")
        assert "[redacted]" in out
        assert "4242" not in out

    def test_a_value_the_guest_supplied_survives(self):
        """The guest gave this address and asked for it echoed back. Redacting it breaks the
        answer and looks like a fault."""
        guest = "my email is grace.hopper@example.com"
        reply = "Confirmed: grace.hopper@example.com"

        assert redact_outbound(reply, allowed=guest) == reply

    def test_the_same_value_is_redacted_without_the_guests_context(self):
        reply = "Confirmed: grace.hopper@example.com"
        assert "[redacted]" in redact_outbound(reply)

    def test_redaction_is_per_value_not_all_or_nothing(self):
        guest = "my email is grace.hopper@example.com"
        reply = "Noted grace.hopper@example.com, but not the card 4242 4242 4242 4242."

        out = redact_outbound(reply, allowed=guest)

        assert "grace.hopper@example.com" in out
        assert "4242" not in out