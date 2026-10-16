"""Turning a reply into just what the guest actually wrote.

When a guest presses Reply, their mail client copies the entire previous exchange underneath their
new message. Left alone, the model reads:

    > On Friday you said the suite was available.
    > What is the rate?

and quite reasonably answers *the hotel's own sentence* rather than the guest's question. Worse, the
quoted part is our own output fed back in as if it were the guest speaking.

So the quoted half has to come off before the text reaches the model. It is the one piece of email
handling with no standard, because every mail client formats its quote markers differently - and a
heuristic that is merely *usually* right leaves the failure in place exactly when a conversation is
long and a reply is short.

**The approach is layered, most-trusted first, because no single signal covers every client:**

1. ``On <date> <someone> wrote:`` and friends - the sentence-form attribution most clients use.
2. An ``On ... wrote:`` line that itself quotes, which some clients nest.
3. A ``-----Original Message-----`` separator, used by several clients and by mailing lists.
4. A run of ``>`` at the start of a line - the oldest convention, and still the most common.
5. Outlook's ``________________________________`` divider.

Every layer is a *stop*, not a filter: the first one that matches ends the new text. Trimming rather
than filtering the markers out is deliberate - if a guest genuinely writes a line starting with
``>``, it is quoted by every client either way and the line is lost regardless.

**A failure here must not lose the message.** :func:`strip_quoted_reply` returns the input unchanged
when it recognises nothing, and the caller falls back to the raw body. A message with a long quoted
tail is far better than no message at all.
"""

from __future__ import annotations

import re

#: "On 3 Nov 2026 at 10:22, Amina Okello wrote:" and its many spellings. Matched case-insensitively
#: and tolerantly on the date, because nobody agrees on a date format.
_ATTRIBUTION = re.compile(
    r"^\s*on\b.{0,200}?\bwrote\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Some clients nest the attribution inside the quoted block rather than before it.
_NESTED_ATTRIBUTION = re.compile(
    r"^\s*>?\s*on\b.{0,200}?\bwrote\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: A separator rather than a sentence - unambiguous, and used by mailing lists and several clients.
_ORIGINAL_MESSAGE = re.compile(
    r"^\s*-{2,}\s*original message\s*-{2,}\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Outlook's long underscore run, which is not a sentence at all.
_OUTLOOK_DIVIDER = re.compile(r"^_{10,}\s*$", re.MULTILINE)

#: A line beginning with `>` - the oldest and still the most common convention. Any run of these,
#: optionally separated by blank or attributed lines, ends the new text.
_QUOTED = re.compile(r"^\s*>", re.MULTILINE)


def strip_quoted_reply(raw: str) -> str:
    """Return only the part the guest wrote this time.

    Returns ``""`` when the whole message looks quoted - an empty reply is a real thing (someone
    pressing Reply and sending nothing but a signature line) and the caller decides what to do.

    The input is returned unchanged when nothing matches, so an unfamiliar format degrades to "the
    guest's message, with its history attached" rather than to nothing.
    """
    if not raw:
        return ""

    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    # Earliest match wins across all the sentence/separator forms, because a client that writes
    # "On ... wrote:" mid-message would otherwise be cut at the wrong place by a later, weaker
    # marker such as a stray `>` inside the new text.
    boundaries: list[int] = []
    for pattern in (_ATTRIBUTION, _ORIGINAL_MESSAGE, _OUTLOOK_DIVIDER):
        match = pattern.search(text)
        if match:
            boundaries.append(match.start())

    # `>` is weaker than the others: it can appear in ordinary text, so it only wins if it starts
    # near the beginning. Requiring it to be in the first portion stops a guest writing "> that was
    # my question" in the middle of a message from truncating everything after it.
    quoted = _QUOTED.search(text)
    if quoted and quoted.start() < len(text) * 0.5:
        boundaries.append(quoted.start())

    nested = _NESTED_ATTRIBUTION.search(text)
    if nested:
        boundaries.append(nested.start())

    if not boundaries:
        return text.strip()

    cut = min(boundaries)
    return text[:cut].strip()


def looks_like_reply(raw: str) -> bool:
    """True when the message quotes earlier conversation.

    Used to decide whether a message is worth answering at all: a guest who presses Reply and sends
    nothing but their old message back has not asked anything, and answering "how can I help?" to it
    is noise.
    """
    if not raw:
        return False
    return bool(
        _ATTRIBUTION.search(raw)
        or _ORIGINAL_MESSAGE.search(raw)
        or _OUTLOOK_DIVIDER.search(raw)
        or _QUOTED.search(raw)
    )


__all__ = ["looks_like_reply", "strip_quoted_reply"]