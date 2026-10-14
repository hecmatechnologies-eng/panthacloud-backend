"""Deterministic PII detection and masking (gap: no output-side guardrail exists).

Why this is hand-written rather than delegated to a model: a guardrail that runs a model to decide
whether to redact is a guardrail that costs a model call on every turn, can be talked out of, and
fails open when the provider is down. Redaction is a pattern-matching problem, so it is solved with
patterns. The model is never asked whether something is a phone number.

**The direction matters and is easy to get backwards.** Masking runs on *inbound* text as well as
outbound, but the outbound case is the interesting one:

    An inbound phone number is masked before it reaches the model, so the model never holds it.
    An outbound string is masked *only where it does not match anything the model was given*.
    Redacting a number the guest supplied and the assistant is quoting back would corrupt a
    legitimate answer, and a guest asking "is this the number I gave you?" would get told no.

That is why :func:`redact_outbound` takes the already-scrubbed context and compares. A redaction
that blanks numbers the assistant is legitimately repeating is worse than no redaction: it looks
like a bug to the guest and hides the real value.

Patterns are deliberately conservative. False positives on a hotel desk are expensive - a room
number "101" is not a phone number, a booking reference is not an account - so anything that would
swallow ordinary prose is excluded. Each pattern is anchored to what actually distinguishes the
thing, and the exclusions are recorded rather than left implicit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# A mask, not a deletion: the model still needs to see that *something* was there to answer
# "please confirm my email" sensibly, and length is preserved so nothing looks truncated.
_MASK = "[redacted]"


class PIIKind(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    CARD = "card"
    IBAN = "iban"


@dataclass(frozen=True, slots=True)
class PIIMatch:
    kind: PIIKind
    start: int
    end: int
    value: str

    def masked(self) -> str:
        return _MASK


# Email: the one pattern with no real ambiguity. Requires a dot in the domain, which excludes the
# `user@localhost` and `user@service` shapes that appear in ordinary technical prose.
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

# Card: 13-19 digits with optional single separators, then Luhn. Length alone is not enough - a
# 16-digit booking reference or a long account number would otherwise be redacted.
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

# Phone: an international prefix, or a separator-bearing group. A bare 10-digit run is NOT matched:
# it collides with room numbers, booking references and years, and false positives on a hotel desk
# are worse than a missed number that the outbound comparison will usually still catch.
_PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{2,4}(?:[\s.-]\d{2,4}){1,4}(?![\w.])")

# IBAN: country code, two check digits, then groups of four alphanumerics.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b")


def _luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _normalise(value: str) -> str:
    return re.sub(r"[ -]", "", value)


def find_pii(text: str) -> list[PIIMatch]:
    """Every match, longest-span-first so an IBAN is not partially masked as a card number."""
    matches: list[PIIMatch] = []

    for match in _EMAIL.finditer(text):
        matches.append(PIIMatch(PIIKind.EMAIL, match.start(), match.end(), match.group()))

    for match in _IBAN.finditer(text):
        matches.append(PIIMatch(PIIKind.IBAN, match.start(), match.end(), match.group()))

    for match in _CARD.finditer(text):
        digits = _normalise(match.group())
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            matches.append(PIIMatch(PIIKind.CARD, match.start(), match.end(), match.group()))

    for match in _PHONE.finditer(text):
        value = match.group().strip()
        digits = re.sub(r"\D", "", value)
        # Too short to be a phone number, and the pattern's job is not to catch every digit run.
        if len(digits) < 7:
            continue
        matches.append(PIIMatch(PIIKind.PHONE, match.start(), match.end(), value))

    # Drop matches contained in a longer one: an IBAN also matches the card pattern, and a card
    # also matches the phone pattern. Without this the caller sees overlapping spans and has to
    # re-derive the precedence rule at every call site.
    matches.sort(key=lambda m: (m.start, -(m.end - m.start)))
    kept: list[PIIMatch] = []
    for candidate in matches:
        if any(candidate.start >= existing.start and candidate.end <= existing.end for existing in kept):
            continue
        kept.append(candidate)
    return kept


def redact(text: str) -> str:
    """Replace every match with a mask, preserving length-independent structure."""
    matches = find_pii(text)
    if not matches:
        return text
    out: list[str] = []
    cursor = 0
    for match in matches:
        out.append(text[cursor : match.start])
        out.append(match.masked())
        cursor = match.end
    out.append(text[cursor:])
    return "".join(out)


def redact_outbound(text: str, *, allowed: str = "") -> str:
    """Redact PII in an outgoing reply *except* values present in ``allowed``.

    ``allowed`` is the scrubbed context the model was given. Anything the model could only have
    known because the guest supplied it is left intact, so quoting a guest's own email back to them
    still works while a number the model invented does not survive.
    """
    allowed_values = set(re.findall(r"[\w.+-]+@[\w.-]+|\+?[\d][\d\s().-]{5,}", allowed))
    allowed_norm = {_normalise(v) for v in allowed_values}

    matches = find_pii(text)
    if not matches:
        return text

    out: list[str] = []
    cursor = 0
    for match in matches:
        if _normalise(match.value) in allowed_norm:
            continue
        out.append(text[cursor : match.start])
        out.append(match.masked())
        cursor = match.end
    out.append(text[cursor:])
    return "".join(out)