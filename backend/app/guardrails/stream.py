"""Lagged redaction for streamed replies.

A streamed reply is already on the guest's screen; it cannot be taken back. So the check cannot
happen "before sending" the way it does on the non-streaming path — it has to happen *behind* the
text, by not sending the risky part until it is provably safe.

**How the lag works.** Deltas accumulate in a buffer and only the portion older than the hold-back
is emitted. So at any moment the guest has seen everything except the trailing window, and that
window is what a PII match would have to be inside in order to be still undetectable. When the
stream ends, the remaining window is redacted with the same rule the non-streaming path uses and
flushed. The guest sees typing throughout; what they never see is a number that only becomes
identifiable in the last few characters.

**Why 64 characters.** It has to exceed the longest span any pattern can match, or a match that
straddles the boundary is emitted unredacted. Measured against the patterns in
:mod:`app.guardrails.pii`: an IBAN is the longest bounded case at about 43 characters, a
space-separated card at 37, a phone at about 34.

**The honest limit.** An email address has no upper bound — the local part is `[\\w.+-]+`. A
deliberately constructed address longer than the hold-back could straddle it. Making the window
unbounded would mean never streaming, so this is a real residual risk rather than a solved problem,
and it is stated in the constant's name so nobody reads the lag as a guarantee.

What it does buy is the common case: a card, a phone number or a normal address produced by a
model reasoning about a booking, rather than an adversary crafting a maximal-length string to walk
through a 64-character window.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.guardrails import redact_outbound
from app.llm.base import ModelDelta, ModelStreamEvent, StreamDone

# Longer than every bounded PII pattern; see the module docstring for the measured spans.
PII_HOLDBACK = 64


async def guard_stream(
    source: AsyncIterator[ModelStreamEvent], *, allowed: str = ""
) -> AsyncIterator[ModelStreamEvent]:
    """Re-emit a provider stream with PII held back, then redacted at the close.

    ``allowed`` is the context the model was shown, exactly as for the non-streaming path: a value
    the guest supplied survives, so an assistant repeating a guest's own address is not broken by
    the guardrail.
    """
    buffer: list[str] = []
    done: StreamDone | None = None

    async for event in source:
        if isinstance(event, StreamDone):
            done = event
            continue
        if not isinstance(event, ModelDelta):
            continue

        buffer.append(event.text)
        joined = "".join(buffer)
        # Everything except the trailing window has been judged safe to show.
        if len(joined) > PII_HOLDBACK:
            emit, held = joined[:-PII_HOLDBACK], joined[-PII_HOLDBACK:]
            buffer = [held]
            if emit:
                yield ModelDelta(text=emit)

    tail = "".join(buffer)
    redacted_tail = redact_outbound(tail, allowed=allowed)
    if redacted_tail:
        yield ModelDelta(text=redacted_tail)

    if done is not None:
        # The terminal event carries the whole answer for the persistence path, so it is redacted
        # as a whole rather than by replaying the deltas: the lag above may have split a match
        # across two emissions.
        yield StreamDone(
            text=redact_outbound(done.text, allowed=allowed),
            model=done.model,
            provider=done.provider,
            usage=done.usage,
        )