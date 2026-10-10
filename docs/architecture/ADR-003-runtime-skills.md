# ADR-003 — Runtime skills and routing: multi-domain capability

**Status:** Accepted · **Date:** 2026-10-11 · **Amends:** ADR-002 (scope) · **Related:** ADR-001

---

## Context

ADR-002 settled the K Hotels question correctly: an approval gate is a state machine on a
turn, the idle-outcome classifier is deterministic, and the runtime should not pay loop cost
on every visitor. What ADR-002 did not consider is that the platform is intended to serve
**multiple domains**, and that requirement is not reachable through instructions plus
documents.

The runtime today is a single generic workflow. The entire behaviour is one function:

```python
# app/runtime/chat.py:398-412
messages = [ModelMessage(role="system", content=assistant.instructions)]
messages += [...history...]
messages.append(ModelMessage(role="user", content=_compose_user_turn(question, retrieved)))
```

No domain branching, no routing, no tools. Tenant configuration is
`Assistant.system_instructions` — and `app/runtime/assistant.py:88-99` is decisive: tenant
instructions are *appended to* the platform contract and *"never override the rules above."*
That is a correct safety property, but it caps what a tenant can express at **tone and domain
detail**.

A hotel fits that ceiling. A bank that must read an account balance, a clinic that must book
an appointment, or a landlord that must check tenancy dates do not — none of those can be
expressed as prose over a document corpus. **ADR-002's "Enforced by" clause naming the
absence of a `tools` field on `ModelRequest` as the boundary therefore forecloses a real
requirement, and this ADR widens it.**

Three questions were open. They are answered here rather than deferred.

---

## Decision

**The runtime gains a per-domain skills registry and a routing step. The default path remains
tool-less. Nothing executes that the platform did not itself ship.**

### D1 — Skills are declarative specs bound to first-party executors

A **skill** is a tenant-declared specification: name, trigger description, input schema,
parameter bindings. It contains **no executable code**. It binds to an executor the platform
ships, registered in code alongside the tenant data.

- Tenant authors data. Platform ships behaviour.
- The attack surface is "which executors exist" — a small, reviewable set.
- MCP-style process isolation is **deferred**, not dismissed: when third-party or
  customer-authored *code* is accepted, a gateway goes in front and nothing executes inline.

### D2 — Routing is deterministic first, model only on ambiguity, reusing signals already computed

The platform already performs retrieval on every turn. Its score is therefore free. Routing
uses it:

| Signal | Route |
|---|---|
| Strong retrieval grounding, no skill trigger matched | **Simple path** — assemble and answer. No extra model call |
| A skill's trigger matches the question | **Skill path** — execute, then draft |
| Weak grounding *and* no trigger match | **Classifier** — one model call to decide |

No routing cost is added to the common case. Rules handle the unambiguous majority; the model
handles only what rules cannot. New domains work without new routing code.

### D3 — Approval attaches to the externally-visible effect, not to the computation

Each executor is registered with an **effect class** in platform code:

| Effect class | Example | Approval |
|---|---|---|
| `read` | `check_availability`, `check_balance` | None. Runs inline |
| `write_external` | `book_room`, `charge_card`, `send_message` | Draft → approval gate → send |

**The tenant cannot set the effect class.** It is a property of the executor registration, so
a misconfigured or hostile tenant cannot mark a charge as a read.

---

## Rationale

- **Multi-domain support needs a capability seam, not a loop.** A workflow can route. What it
  cannot do is acquire a capability it was not built with.
- **This is what concept 7 means.** A skill is "name + description, rules, identify input →
  execute action → deliver output" — reusable instructions an agent reuses. That is precisely
  what a domain registers.
- **Least Agency is preserved structurally.** The default path stays tool-less. Tools are
  per-domain, declared, and gated by an effect class the tenant does not control. This is
  *more* aligned with NIST's Least Agency principle than a blanket agent loop would be.
- **Cost discipline is preserved.** The routing signals reuse computation already performed,
  so the simple path costs the same model call it does today.
- **It reuses the prototype's existing shape.** The Approvals tab is exactly the
  `write_external` gate; the Follow-up list is deterministic. No new product concepts.

---

## Alternatives considered

| Option | Rejected because |
|---|---|
| **Make every runtime turn an agent loop** | Pays loop cost and latency on the ~90% of turns that are questions with good answers, and surrenders the structural least-agency property that is currently the strongest OWASP/NIST alignment. Anthropic's own guidance is to *"use the simplest solution possible."* |
| **Tenant-authored skill code, executed in-process** | Arbitrary code execution in our process is ASI05. The sandbox is a path check. Unacceptable. |
| **MCP from day one** | Unit 42 measured a **78.3% attack success rate** with five MCP servers attached to one agent; 30+ MCP CVEs were filed in early 2026. Adopting it before the tool count justifies the boundary inverts the risk. |
| **A configurable workflow DSL per domain** | Defers the same capability problem into an engine we would have to design, document and secure — and would still require a per-domain decision point. Skills are smaller and reuse the existing approval machinery. |
| **A model classifier on every turn** | Adds a model call and latency to every visitor turn, including the trivial ones, to make a decision that retrieval already largely answers. |

---

## Consequences

**Positive** — the runtime gains a seam for new domains that requires no architectural change;
least agency, budget enforcement and approval gating all carry over; the tool surface stays
platform-controlled.

**Negative** — `ModelRequest` gains a `tools` field, which touches the shared provider
protocol and every adapter. A second executor surface exists alongside the engineering tool
gateway and must not be conflated with it. Skills become a product concept that tenants must
be taught, and a badly described skill will simply never trigger. Routing quality is now a
correctness concern, which makes evals a prerequisite rather than a nice-to-have.

**Prerequisite:** runtime evals (`TODO-KHOTELS-EVOLUTION.md` K7, gap G1) must land **before**
skills. Executing tenant-declared capabilities against guest-facing data without regression
detection is the risk this ADR creates.

---

## Enforced by

- `app/llm/base.py` — `ModelRequest.tools` must remain **optional and empty by default**. A
  turn with no declared skill must produce byte-identical behaviour to today.
- `fussion-reviewer` — `app/runtime/` still must not import `app/agents/` or engineering
  tools. Skills bind to runtime executors, never the engineering `ToolGateway`.
- New rule required: **tenant-declared skills may not carry executable code, and may not set
  their own effect class.** Both are properties of platform registration.

---

## Revisit trigger

- **MCP or any out-of-process tool boundary** — the moment third-party-authored tools are
  accepted, not before.
- **A skill that must chain into another skill with parameters derived from the first** —
  genuine multi-step reasoning, at which point the simple/skill split needs a real loop.
- **Cross-domain agent federation** — when tenants expose agents *to each other*, A2A becomes
  relevant; it is not relevant to K Hotels.

---

*Related: `standards-alignment.md` (G1 evals is the prerequisite; LLM03 Excessive Agency and
NIST Least Agency are what this design protects), `TODO-KHOTELS-EVOLUTION.md`,
`TODO-INTEGRATION.md` (L0/L1/L3 revised here).*