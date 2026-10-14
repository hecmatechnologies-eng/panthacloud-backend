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

**Action:** ~~write `docs/architecture/ADR-002-runtime-loop-not-required.md`~~ — **done**, as
`docs/architecture/ADR-002-no-runtime-agent-loop.md`. Short. Its job is to stop the question
being re-opened, and to name the trigger above.

> ⚠️ **Amended by `ADR-003-runtime-skills.md` (2026-10-11).** The reasoning above is correct for
> K Hotels and still holds — the default runtime path stays tool-less, an approval gate is a
> state machine, and the idle classifier is deterministic. But it foreclosed a requirement the
> brief now makes explicit: serving **other domains**. Prose over a document corpus cannot
> express "read this account balance" or "book this appointment", because
> `runtime/assistant.py:88-99` caps tenant instructions at tone and domain detail.
>
> ADR-003 adds a per-domain skills registry and a routing step. **K Hotels itself needs none
> of it** — K1–K7 below are unaffected and proceed as written. The skills work is future-domain
> scope and is tracked in `TODO-INTEGRATION.md` L0/L1.

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
so citations are suppressed on refusal.

> **Update 2026-10-14:** the behaviour is now pinned as a contract by K7's
> `weak_retrieval_is_excluded_by_the_threshold` case, which fails if a sub-threshold chunk is
> quoted or cited. Raising the deployment default `RETRIEVAL_SCORE_THRESHOLD` from `0.0` is still
> open, and remains a product decision rather than an evaluation one.

### K2 — Write ADR-002 · ✅ **DONE 2026-10-11**

Written as `docs/architecture/ADR-002-no-runtime-agent-loop.md`. Records the decision, the
alternatives, and the revisit trigger. Cross-referenced from ADR-001 §4 and `CLAUDE.md` §5,
both of which are **upheld, not amended** — no import rule was relaxed.

### K3 — Session-outcome state · ~2h

Migration `0031`. Add to `VisitorSession`: last-inbound timestamp, analysed flag, outcome
(`converted` / `not_converted` / `None`). Prototype rule: `lastSeen` = when inbound stopped;
at 15 min idle classify. **Done when:** the migration applies and a session can be marked analysed.

### K4 — 15-minute idle analyser · ~1 day

`app/jobs/tasks.py` + a cron job on the existing ARQ worker. Deterministic, no LLM.

> ✅ **The scheduler now exists.** `app/jobs/scheduler.py` plus `cron_jobs` on `WorkerSettings`
> (registered 2026-10-11, verified live: the worker logs `Starting worker for 3 functions`).
> The first cron is the knowledge reaper; K4 adds a second alongside it. `unique=True` on each,
> so several workers never run the same maintenance job concurrently.
>
> Note: **arq 0.28.0 has a bug** — `CronJob` is a dataclass with no field defaults, so all
> fourteen arguments must be passed explicitly. `worker.py` does that with a comment; a canary
> test in `tests/test_knowledge_reaper.py` will fail when arq fixes it, at which point the
> workaround can be collapsed.

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

### K7 — Runtime evals · ✅ **DONE 2026-10-14**

> **Correction to the premise this item was written under.** It previously read: *"`app/evals/`
> covers only `website_analyst` today, and the 9 existing cases are **not referenced in
> `.github/workflows/ci.yml`** — so they are not a gate."* That was wrong on both counts.
> `ci.yml` had a "Run Evals" step on `tests/test_evals.py`, and those 9 cases are model-free
> (`deterministic_analyze`), so they were already gating. The real gap was never CI wiring — it was
> that **nothing evaluated the guest-facing runtime at all**.

**What landed.** `app/evals/runtime_corpus.py` + `runtime_runner.py`, gated by
`tests/test_runtime_evals.py` and its own CI step. Ten cases driving real
`POST /api/v1/public/chat` turns through the ASGI app, with the model faked and retrieval stubbed
per case. Each case drives a full turn rather than one function, because the properties span HTTP
tenant resolution, rate limiting, prompt assembly, the gateway and persistence.

| Case | Property |
|---|---|
| `grounded_answer_cites_the_document_it_used` | a grounded answer carries the citation for the chunk it was given, fenced in the user turn |
| `no_knowledge_base_says_so_rather_than_inventing` | nothing retrieved ⇒ the prompt states it, no fence, no citations |
| `poisoned_document_cannot_forge_the_fence` | a document carrying the closing delimiter cannot escape the data region |
| `unconfigured_tenant_still_gets_the_platform_contract` | absence of configuration is never the absence of the contract |
| `tenant_instructions_are_appended_below_the_contract` | tenant rules extend, never replace, the platform layer |
| `hostile_tenant_instructions_cannot_widen_the_contract` | tenant text requesting elevated capability does not grant it |
| `weak_retrieval_is_excluded_by_the_threshold` | an irrelevant chunk below the threshold is neither quoted nor cited |
| `citation_markers_are_rank_not_chunk_index` | `[n]` is retrieval rank; `chunk_index` is a separate numbering space |
| `history_is_carried_oldest_first_with_the_question_last` | follow-ups see prior turns; the current question is never replayed as history |
| `every_reply_carries_its_provenance` | `assistant_version` + `prompt_hash` recorded per reply |

**`weak_retrieval` closes the K1 tuning note** (§ below, "Minor tuning note"). It is treated as a
contract rather than cosmetics: those 0.42–0.47 citations are what a visitor is told the answer
came from, and they are the signal ADR-003's router decides on. The corpus pins the *handling*; the
deployment default `RETRIEVAL_SCORE_THRESHOLD` is still `0.0` and remains a product decision.

**What this corpus cannot decide, stated plainly.** It never calls a model, so it cannot verify
that the model *refuses* a weakly-grounded question — that judgement happens inside the model. What
it verifies is what the runtime owns: the prompt it assembled, the citations it claimed, and its
behaviour when retrieval returns nothing or something irrelevant. Judging model grounding needs a
live model and belongs in an out-of-band run, not a PR gate.

**Verified by mutation, not by passing.** Six runtime guarantees were disabled in turn and the
corpus required to catch each. One did not fire, and it was the corpus that was wrong:

> The injection case asserted `"UNTRUSTED CONTENT" is present` as proof the fence survived. It
> could never fail — the fence's own closing delimiter contains that phrase, and so does the
> attacker's payload. **The case passed with `fence_untrusted` deleted from the runtime.** A green
> case guarding nothing. Replaced with exact sentinel counting (one opening, one closing, payload
> defanged), which fails when the fence is removed *or* forgeable.

That is the fourth time this session a passing test turned out to prove nothing. Two of my own
corpus cases also shipped an unconditional assertion that fired on success —
`f"status {o.status_code}, expected 200"` reported failure for a correct 200, in all ten cases.

---

## 4. What this removes from `TODO-INTEGRATION.md`

The L0–L6 plan was written assuming a runtime agent loop. On this framing:

| Level | Change |
|---|---|
| **L0** Platform core (runtime loop + tool registry) | **No loop** (ADR-002). But a runtime **tool registry** returns via ADR-003 — per-domain declarative skills bound to first-party executors, not a general tool protocol |
| **L1** `OrgAgentPolicy` | **Shrinks hard** — `system_instructions` + rate limits + budgets already are most of it. ADR-003 moves the *capability* dimension into the skills registry, so L1 becomes bounds only (spend, idle threshold, autonomy tier) |
| **L3** Shared runtime agent (lead-capture write, escalation path) | **Largely evaporates for K Hotels** — with staff approving, staff take the lead. Returns for later domains once ADR-003 skills exist |
| L2 Colleague agents | unchanged |
| L4 Channels | unchanged |
| L5 Staff surfaces | unchanged — this is K6 |
| L6 Evals | unchanged — this is K7 |

Do not re-derive these; treat the L0/L1/L3 rows as superseded by this document.

---

## 5. Explicitly not building

Recorded so these do not creep back in:

- **A runtime agent loop.** See §1. ADR-003 adds capabilities, not a loop.
- **Runtime skills, for K Hotels.** ADR-003 opens the seam for *later* domains. K Hotels is
  served by retrieval + drafts + staff approval and needs no skill. Building an executor now
  would be scope creep — wait for a second tenant that actually needs one.
- **A `tools` field on `ModelRequest`/`ModelMessage`.** The MVP does not need it; adding it
  would touch the shared provider protocol and every adapter for a use case not yet proven.
- **A2A / MCP.** Greenfield, no current requirement.
- **Runtime "skills"** (`skills/integrations/*` are engineering-plane only). If hotel-specific
  capability is needed later, `system_instructions` is the existing seam — use it first.

---

## 6. Open questions

- **What gets retained from a guest conversation.** Recorded 2026-10-14, deliberately not yet
  decided. A guest's message is persisted verbatim in `Message.content`, so anything they type into
  the widget — an email, a phone number, a card number — is stored in the clear. The **outbound**
  guardrail (§ guardrails, `app/guardrails/pii.py`) stops a model-invented value reaching a guest or
  the database, and it covers every channel per ADR-004. It does not touch what the guest typed, and
  it should not: redacting inbound before the model sees it stops the assistant confirming an address
  back, which is the job.
  
  So the open question is not a guardrail question, it is a **data-retention policy**: store the raw
  message, or store a redacted copy with the raw held for a bounded window for support purposes?
  Whatever is chosen needs a written retention window and an erasure path, because a hotel handling
  guest contact details is exactly the case where "we'll decide later" turns into an incident. Worth
  settling before a real guest types a card number, not after.

- **A channel adapter bypassing the turn path.** ADR-004 records the rule that channel adapters must
  reach the model through `app.runtime.chat.handle_chat`, so they inherit the outbound guard and the
  budget. That rule is currently only a docstring. It needs a test: an adapter holding its own
  `ModelGateway` must not be able to send unredacted.

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