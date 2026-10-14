# ADR-004 — Channel delivery semantics and the streaming guardrail

**Status:** Accepted · **Date:** 2026-10-14 · **Related:** ADR-002, ADR-003

---

## Context

The runtime has exactly one customer surface today: a web widget that streams its reply, so text
appears as the model writes it.

Channels change that. Email has no partial-message concept at all; a message that assembles itself
in the recipient's view reads as broken rather than responsive. WhatsApp is the same, and it offers
a *better* affordance for the same need — a typing indicator, which signals activity without putting
half a sentence in front of a guest.

Streaming a widget's behaviour into either channel would be a UX regression dressed up as
consistency.

This matters beyond taste, because the outbound guardrail's cost is different per delivery mode. On
the non-streaming path the whole reply exists before anything is returned, so it can be checked and
redacted with no compromise. On the streaming path a delta already on a guest's screen cannot be
retracted, so the check has to happen *behind* the text by lagging it — see
`app/guardrails/stream.py`.

---

## Decision

**Streaming is a property of the channel, not of the runtime.**

- **Web widget** — streamed, with the lagged outbound guardrail. The lag holds back a 64-character
  window, which exceeds the longest span any PII pattern can match, and flushes it redacted at the
  close.
- **Email** — one complete message. Typing indicator: none.
- **WhatsApp / Telegram / any future channel** — typing indicator while the model works, then one
  complete message.

**Every non-streaming channel goes through the existing non-streaming turn path** rather than
growing its own send logic. That is not tidiness: it is what makes the guardrail apply by
construction instead of by remembering.

## Consequences

**Positive** — the guardrail has no unguarded surface once the channels land. The lag, which is the
expensive half of the guard, is paid only where streaming is genuinely wanted. Channel adapters stay
thin: normalize an inbound payload, call the turn, normalize an outbound one.

**Negative** — a channel adapter that calls the provider directly would bypass both the guardrail
and the budget. That is the failure mode to test for, not to warn about in a docstring.

**A limit that stays.** An email address has no maximum length, so a deliberately constructed one
longer than the hold-back can still straddle the window on the web widget. Making the window
unbounded means never streaming. This is accepted: the residual risk is an adversary crafting a
maximal-length string, against the realistic case of a model reasoning about a booking.

---

## Enforced by

- `app/guardrails/stream.py` — the lag, and the window-size test that pins it against the patterns.
- **New rule required:** channel adapters must reach the model through `app.runtime.chat.handle_chat`,
  never by holding a `ModelGateway` of their own. A test should assert an adapter cannot redact its
  way past the outbound guard.

---

## Revisit trigger

- A channel where partial delivery is the *expected* convention — a live-chat product, or a
  collaborative document surface. Then streaming is per-channel already, and this decision holds.
- A channel with no typing indicator and long generation times, where silence reads as failure.
  The answer there is an interim message, not partial delivery.

---

*Related: `app/guardrails/pii.py`, `app/runtime/chat.py::_stream_events`, ADR-003 (skills attach to
the approval gate, which is channel-independent), `TODO-KHOTELS-EVOLUTION.md`.*