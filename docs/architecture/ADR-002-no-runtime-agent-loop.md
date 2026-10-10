# ADR-002 — K Hotels does not require a runtime agent loop

**Status:** Accepted · **Date:** 2026-10-11 · **Supersedes:** none · **Amends:** ADR-001 §4
· **Amended by:** [ADR-003](ADR-003-runtime-skills.md) (2026-10-11)

---

## Context

ADR-001 §4 decided that "the runtime plane uses no framework. `retrieve → assemble → stream`
is a direct provider call," and `CLAUDE.md` §5 restates it: *"Two planes, deliberately
asymmetric. The engineering agent runs a full loop with tools, budgets, and approval gates.
The visitor runtime is a single-turn pipeline… Do not force the runtime through the agent
loop; it has different volume, latency, and risk."* `fussion-reviewer` enforces the related
import rule that `app/runtime/` must not import `app/agents/` or engineering tools.

The K Hotels work appeared to require reversing this. Its guest desk has staff **approving**
replies before they are sent, and the reasoning was: to approve something the system must be
able to *do* something; to do something the runtime needs tools; tools imply a loop; a loop
reverses ADR-001 §4 and `CLAUDE.md` §5.

That chain was investigated rather than assumed. Two findings dissolve it.

**The loop is not what implements an approval gate.** Holding a drafted reply for human
review is a state machine on a turn — `pending → approved → sent`. It needs no
`AgentDefinition`, no `AgentRun`, no harness, and no model decision after an observation. The
runtime already has the pieces: `Message` carries `citations` and `assistant_version` /
`prompt_hash` per reply, `Conversation` carries the thread, and `Assistant.system_instructions`
is read live as the tenant's instructions (`app/runtime/assistant.py:101`) — that is the
per-organisation policy surface, and it already exists.

**The runtime could not loop today anyway.** `ModelRequest` and `ModelMessage`
(`app/llm/base.py:14-25`) carry no tools field at all. Tool calling lives exclusively in
`app/llm/adapters/pydantic_ai_runner.py`, behind the `AgentRunner` protocol — the engineering
path. The runtime calls `ModelGateway.stream()` with text in and text out.

The same reasoning applies to the K Hotels session-outcome rule (idle 15 minutes, then
`+ converted` ⇒ Success / `− not converted` ⇒ Follow-up sent). That is a deterministic
classifier over `VisitorSession`, not a reasoning step. Running it behind an LLM loop would
cost more and decide less reliably.

---

## Decision

**Do not add a runtime agent loop, and do not add a `tools` field to the shared model
request. K Hotels is served by the existing runtime as it stands, plus small additive
changes.**

ADR-001 §4 and `CLAUDE.md` §5 stand unchanged. Nothing in the import rules is relaxed, so
`fussion-reviewer` needs no change — which is the strongest evidence that this is an
evolution of the architecture rather than a change to it.

K Hotels is delivered as: existing capabilities, plus a scheduled job for the idle trigger,
a small amount of session-outcome state, an approval state machine, and staff UI. None of
these reach into the agent layer.

---

## Rationale

- **The design is human-in-the-loop by intent.** The Approvals tab exists so staff review
  before anything is sent. If a human decides every outbound action, the agent's job is
  *retrieve and draft*. It never needs a write tool, let alone a loop.
- **Cost and latency.** The runtime is the highest-volume path in the product. A loop
  multiplies model calls per turn. For the overwhelming majority of hotel questions —
  prices, amenities, policies — retrieval plus one assembled turn is the whole job.
- **Blast radius.** Adding tools to the shared provider protocol touches every adapter and
  every caller, on the path serving every visitor, for a capability not yet demonstrated to
  be needed.
- **The requirement is satisfied elsewhere.** Every capability the K Hotels design actually
  exercises is already present: per-tenant instructions, session and conversation
  persistence, per-message citations and provenance, three-tier rate limiting
  (IP / integration / organization), per-organisation spend budgets, and an org-scoped
  knowledge base. Verified working end to end.

---

## Alternatives considered

| Option | Rejected because |
|---|---|
| **Give the runtime a bounded agent loop** | Buys a loop for a use case that does not exist. The approval gate is a state machine, not a loop. Multiplies cost and latency on the highest-volume path, and would require relaxing `CLAUDE.md` §5 and the reviewer's import rule for no gain. |
| **Route the runtime through the engineering harness** | Merges the two planes ADR-001 deliberately separated. Customer-facing spend would share one budget with internal engineering spend, and visitor conversations would pass through the engineering audit surface. Strictly more risk on the path that matters most. |
| **Add `tools` to `ModelRequest` without a loop** (single-step tool use) | Technically the smallest of the three and the correct answer *if* the assistant must read live availability. K Hotels as currently designed does not require it — staff take the action. Deferred rather than rejected; see the trigger below. |
| **Keep `Assistant.system_instructions` as the only per-tenant policy** *(accepted)* | It is the existing seam, it is already read live, and it carries the tenant's tone and rules today. Building a new `OrgAgentPolicy` model before anything needs one would duplicate a field that works. |

---

## Consequences

**Positive** — K Hotels ships without reversing a single architectural decision; the
reviewer's machine-checked rules stay intact; no new dependency on the shared provider
protocol; the runtime keeps its latency and cost profile.

**Negative** — staff become a throughput ceiling, since every outbound reply needs human
approval; that is a deliberate product choice, not an oversight, and it is the thing to
revisit if reply volume outgrows it. The per-organisation policy surface is currently a
5,000-character instruction string rather than a structured model, which is adequate for
tone and rules but not for numeric bounds such as spend caps or the 15-minute threshold. The
idle threshold is currently a constant rather than per-organisation.

---

## Enforced by

- `.claude/agents/fussion-reviewer.md` — `app/runtime/` must not import `app/agents/` or
  engineering tools (**unchanged by this ADR**).
- `app/llm/base.py` — the absence of a `tools` field on `ModelRequest` / `ModelMessage` is
  what makes "no runtime tool calling" a structural property rather than a convention. Adding
  one is a deliberate change to this ADR.

> **Amended by ADR-003 (2026-10-11).** This clause held for K Hotels, but the platform is
> intended to serve multiple domains, and prose over a document corpus cannot express "read
> this account balance" or "book this appointment". ADR-003 adds a per-domain skills registry
> and a routing step, and introduces `ModelRequest.tools` as **optional and empty by default**.
> The reasoning below still stands: the default path remains tool-less, an approval gate is
> still a state machine rather than a loop, and the idle classifier is still deterministic.

---

## Revisit trigger

Reopen this decision when **the assistant must decide what to do after observing a tool
result** — that is, when it has to choose to continue rather than draft for a human to act.
Concrete cases that would trigger it:

- verifying a quoted price against live availability before offering it
- re-querying retrieval when the first pass grounds poorly, and judging that itself
- chaining steps where step two's parameters derive from step one's output

Note that **sequential tool calls within a single turn are not this trigger** — every
provider supports them and they require no loop. The trigger is the model choosing whether
to take another step.

Two smaller changes are *not* triggers, and need no ADR:

- a read-only availability tool → add `tools` to `ModelRequest`, amend §"Enforced by"
- a per-organisation idle threshold or spend cap → extend the existing per-tenant
  configuration surface

---

*Related: `TODO-KHOTELS-EVOLUTION.md` (K1–K7), `TODO-INTEGRATION.md` (L0/L1/L3 recorded as
superseded by this framing), `TODO-DEMO-READINESS.md`.*