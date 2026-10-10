# TODO: K Hotels Evolution

> Work to make Fussion serve K Hotels **on top of capabilities it already has.**
>
> **Framing rule: evolve, do not rewrite.** No reversal of ADR-001, no runtime agent loop,
> no new tool protocol, no import of `app/agents/` into `app/runtime/`. Every item below is
> additive and sits on an existing seam.
>
> Companions: `TODO-DEMO-READINESS.md` (embeddings, agent API, frontend slices),
> `TODO-INTEGRATION.md` (the L0–L6 build plan — see §4 for what this document removes),
> and `standards-alignment.md` (position against OWASP LLM/Agentic Top 10 and NIST; gap G3
> there — knowledge ingestion integrity — applies directly to this work).

---

## 1. The decision: no runtime agent loop

**ADR-002 is reframed.** It is no longer "should the runtime get a bounded agent loop."
It becomes a short record of why it does not need one.

The reasoning, for whoever picks this up cold:

- The K Hotels design is **human-in-the-loop by default** — the Approvals tab exists so staff
  review before anything is sent. The agent therefore *retrieves and drafts*; staff act.
- **An approval pause is a state machine on a turn, not an agent loop.** It needs no
  `AgentDefinition`, no `AgentRun`, no harness.
- The 15-minute idle → conversion analysis is **deterministic**. Running it behind an LLM
  loop would be strictly worse.
- The runtime structurally cannot loop today anyway: `ModelRequest`/`ModelMessage` in
  `app/llm/base.py` carry **no tools field**. Tool-calling lives only in
  `app/llm/adapters/pydantic_ai_runner.py`, behind `AgentRunner`, which is the engineering path.

**Trigger that would revive the question:** when the assistant must *decide what to do after
observing a tool result* — verify a quote against live availability, re-query when retrieval
grounds poorly, or chain steps where step 2's parameters derive from step 1's output.

Note this is **not** the same as sequential tool calls within one turn, which every provider
already supports and which need no loop.

**Action:** write `docs/architecture/ADR-002-runtime-loop-not-required.md`. Short. Its job
is to stop the question being re-opened, and to name the trigger above.

---

## 2. Capability map — what already exists

| K Hotels need | Already built | Where | Delta |
|---|---|---|---|
| Per-org behaviour and policy | `Assistant.system_instructions`, read live as `tenant_instructions` | `app/runtime/assistant.py:101` | zero |
| Track a guest over time | `VisitorSession` → `Conversation` → `Message` | `app/models/conversation.py` | zero |
| Grounded answers **with citations** | `Message.citations` (JSON), persisted per reply | `app/models/conversation.py:150` | zero |
| Per-org isolation | Rate limits at IP / integration / **organization** tiers | `app/runtime/chat.py:_prepare_turn` | zero |
| Per-org spend caps | `ModelGateway` budget enforcement | `app/llm/gateway.py` | zero |
| Tenant knowledge base | `KnowledgeBase` per project, org-scoped | `app/models/knowledge.py` | zero — real embeddings now live |
| Staff-configurable assistant | `welcome_message`, `starter_prompt`, brand colours, position, `is_enabled` | `app/models/assistant.py` | zero |
| Reply provenance | `assistant_version` + `prompt_hash` per message | `app/models/conversation.py:162` | zero |
| Async job infrastructure | ARQ worker + task queue | `app/jobs/` | zero |

The five-step prototype model maps onto these directly: **Receive** → `VisitorSession`;
**Understand** → retrieval; **Respond** → `system_instructions` + gateway + citations;
**Escalate** → staff view of existing conversations; **Follow up** → the one real gap (K4).

---

## 3. Work items

Ordered by dependency. **K1 and K2 complete — K3 is next (first real code).**

### K1 — Wire `MODEL_API_KEY` · ✅ **DONE 2026-10-11**

The same Gemini key used for embeddings also serves `gemini-2.5-flash`, so no second
credential was needed. `backend/.env` now sets `MODEL_PROVIDER=gemini`,
`MODEL_API_KEY`, `MODEL_ID=gemini-2.5-flash`, `MODEL_ALLOWED_IDS=["gemini-2.5-flash"]`.
The startup line `No model provider configured; public chat will return 503` is **gone**.

**Verified end to end via `POST /api/v1/public/chat`:**

| Probe | Result |
|---|---|
| "staying with you next month… what would that cost?" | Correctly **refused** — KB holds Panthacloud pricing, not hotel pricing — and cited what it does have |
| Follow-up in same session: "the three plans you just mentioned?" | Recalled turn 1 correctly, cited all three with scores |
| "Does Panthacloud support real-time streaming, how does it avoid leaking styles?" | Answered from retrieval, top citation 0.6488 |
| "What's the capital of France?" | Correctly refused, no fabrication |
| "Can you book me a table at 7pm for four?" | Correctly refused, offered front desk per tenant instructions |

**Dev bootstrap this required** (repeat on any fresh database):
1. org → project (`panthacloud-frontend`) → knowledge base → seeded document
2. a `WebsiteIntegration` row, to get a `public_key`
3. an `AllowedOrigin` row (`http://localhost:3000`, `is_verified=true`) — **without it
   `/public/chat` returns 403 "Unknown client key or unregistered origin"**
4. an `Assistant` row with `system_instructions` — the tenant-policy seam from §2

**Minor tuning note:** refusals still return low-scoring citations (0.42–0.47) even though
the model correctly ignores them. The runtime's internal retrieval threshold could be raised
so citations are suppressed on refusal. Cosmetic; the behaviour is already correct.

### K2 — Write ADR-002 · ✅ **DONE 2026-10-11**

Written as `docs/architecture/ADR-002-no-runtime-agent-loop.md`. Records the decision, the
alternatives, and the revisit trigger. Cross-referenced from ADR-001 §4 and `CLAUDE.md` §5,
both of which are **upheld, not amended** — no import rule was relaxed.

### K3 — Session-outcome state · ~2h

Migration `0031`. Add to `VisitorSession`: last-inbound timestamp, analysed flag, outcome
(`converted` / `not_converted` / `None`). Prototype rule: `lastSeen` = when inbound stopped;
at 15 min idle classify. **Done when:** the migration applies and a session can be marked analysed.

### K4 — 15-minute idle analyser · ~1 day

`app/jobs/tasks.py` + a delayed/cron job on the existing ARQ worker (there is **no** scheduler
configured today — this is the new part). Deterministic, no LLM.

Emits the prototype's outcome model: `+ Converted` ⇒ **Success**; `− Not converted` ⇒
**Follow-up sent**. Feeds the Follow-up list badge (grey when no new, amber when new).

**Done when:** a session idle past 15 minutes is classified without human action.

### K5 — Approval / draft state · ~1 day

New table for outbound actions awaiting staff review: the drafted reply, its source citation,
and states (pending → approved → sent / rejected / escalated). Reuse the
`ApprovedPlan` idea from `app/tools/gateway.py` as the shape, but as a plain state machine.

**Done when:** a drafted reply can be held, approved, and sent — with the guest never seeing
an unapproved message.

### K6 — Staff UI: Approvals + Follow-up tabs · ~2–3 days

On existing Studio patterns (`src/components/shell/`, nav items, existing data hooks). Session
ID first; columns ending **Conversion › Status › Feedback**. Row click opens a right-anchored
detail modal.

The standalone HTML prototype at `frontend/khotels-prototype/khotels-guest-desk.html` is the
reference for layout and behaviour.

### K7 — Runtime evals · ~1 day · 🔴 **raised to G1 by the standards assessment**

Closes the only 🔴 **assurance** gap in `standards-alignment.md`. `app/evals/` covers **only**
`website_analyst` today, and the 9 existing cases are **not referenced in
`.github/workflows/ci.yml`** — so they are not a gate.

NIST's March 2026 automated-benchmark work is expected to define how agent assurance is
measured. K3–K7 are all guest-facing behaviour with no regression detection behind them.

Add a runtime case type: grounding and citation accuracy, refusal when retrieval is weak,
and adherence to per-tenant `system_instructions`. **Wire evals into CI as a gate.**

---

## 4. What this removes from `TODO-INTEGRATION.md`

The L0–L6 plan was written assuming a runtime agent loop. On this framing:

| Level | Change |
|---|---|
| **L0** Platform core (runtime loop + tool registry) | **Largely evaporates** — no loop |
| **L1** `OrgAgentPolicy` | **Shrinks hard** — `system_instructions` + existing rate limits + existing budgets already are most of it. Becomes a thin bounds object, not a new model |
| **L3** Shared runtime agent (lead-capture write, escalation path) | **Largely evaporates** — with staff approving, staff take the lead |
| L2 Colleague agents | unchanged |
| L4 Channels | unchanged |
| L5 Staff surfaces | unchanged — this is K6 |
| L6 Evals | unchanged — this is K7 |

Do not re-derive these; treat the L0/L1/L3 rows as superseded by this document.

---

## 5. Explicitly not building

Recorded so these do not creep back in:

- **A runtime agent loop.** See §1.
- **A `tools` field on `ModelRequest`/`ModelMessage`.** The MVP does not need it; adding it
  would touch the shared provider protocol and every adapter for a use case not yet proven.
- **A2A / MCP.** Greenfield, no current requirement.
- **Runtime "skills"** (`skills/integrations/*` are engineering-plane only). If hotel-specific
  capability is needed later, `system_instructions` is the existing seam — use it first.

---

## 6. Open questions

- Does K Hotels need the assistant to **read live availability**, or is that always a staff
  action? Answer determines whether K1 alone suffices or K5 grows a read-only tool.
- Should the 15-minute threshold be **per-org configurable**? The prototype hard-codes 15.
  If yes, it is a field on the existing per-tenant assistant/policy surface — not a new model.
- **Knowledge ingestion integrity** (`standards-alignment.md` G3): nothing verifies document
  provenance. This got *worse* when Item 1 landed — under hash embeddings a poisoned document
  was only retrievable by keyword match; under real semantic embeddings it is retrievable by
  *meaning*. Every guest answer for K Hotels comes from that corpus. Worth deciding whether a
  document should require tenant confirmation before it becomes `READY`.
- Multi-tenant test coverage: K3–K5 all touch tenancy. Confirm the isolation tests cover the
  new surfaces before shipping.

---

*Created 2026-10-11. K1 (embeddings provider) completed same day; see
`TODO-DEMO-READINESS.md` §1 for the embeddings work it builds on.*