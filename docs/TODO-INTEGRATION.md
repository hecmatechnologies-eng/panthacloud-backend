# TODO: Agent Levels, Org-Scoped Execution, and K Hotels Delivery

> Plan for building Fussion as a two-plane agent system: **colleague agents** (internal,
> engineering plane, run through the harness) plus one **shared runtime agent**
> (customer-facing, resolved per organisation). Every level below states what exists
> in code, what must be built, where, and what it costs. K Hotels is Tenant #1.
>
> **Companion:** `TODO-DEMO-READINESS.md` — the shorter "what is left before an end-to-end
> demo" list (embeddings, agent API, frontend slices). This document is the build plan.
>
> ⚠️ **Partly superseded.** `TODO-KHOTELS-EVOLUTION.md` scopes K Hotels as *evolution on top
> of existing capabilities* rather than new architecture. Under that framing, **L0 and L3
> largely evaporate and L1 shrinks to a thin bounds object.** Read that document before
> starting any L0, L1 or L3 work. L2, L4, L5 and L6 stand.

## 1. The agent model as built (verified in code)

| Piece | File | State |
|---|---|---|
| Agent contract (`AgentDefinition`: name, version, instructions, capabilities, tools, output schema, budget) | `backend/app/agents/base.py` | Built |
| Registry (name plus version, no silent replace) | `backend/app/agents/registry.py` | Built; registers `website_analyst` 1.0.0 and `coding_agent` 1.0.0 |
| Execution context carrying org and project | `backend/app/harness/context.py` (`organization_id`, `project_id`) | Built |
| Tool gateway (single choke point; reads auto-authorised by capability; writes need approved plan; secrets redacted) | `backend/app/tools/gateway.py` (`ApprovedPlan`) | Built |
| Agent runs persisted per org | `backend/app/models/agent_run.py` (`organization_id`, `project_id`, index on org plus created) | Built |
| Agent runs API | `backend/app/api/v1/endpoints/agent_runs.py` | Built |
| Runtime tenancy (`TenantContext`: org, project, integration — frozen, resolved from public key plus origin, single indistinguishable refusal) | `backend/app/runtime/resolver.py` | Built |
| Customer-facing declaration (`CustomerAssistant`: versioned, read-only `knowledge.read`, platform grounding instructions unchangeable by tenant) | `backend/app/runtime/assistant.py` | Built |
| Runtime chat pipeline (resolve, rate-limit, session, retrieve, assemble, stream) | `backend/app/runtime/chat.py` | Built |
| Per-project assistant config (tenant instructions layer) | `backend/app/models/assistant.py` (`system_instructions`) | Built |
| Per-org model choice | `backend/app/models/organization_model_settings.py` | Built |
| Visitor sessions and conversations | `backend/app/models/conversation.py` | Built |

**Design law — REVISED by new decision (supersedes ADR-001 section 4).**

Previously (ADR-001 section 4): the runtime plane runs **no agent loop** — a direct
`retrieve → assemble → stream` provider call, chosen to keep the highest-volume,
lowest-latency path free of agent machinery.

New decision: there is **one shared customer-facing runtime agent**, resolved **per
organisation**, carrying **org-scoped claims, configurations, and execution**. It **runs
tools and acts per org level** within the bounded autonomy model (inform versus commit).
The runtime is therefore a **bounded agent loop**, not a direct call.

Consequences that must be honoured:

1. A **superseding ADR** (`docs/architecture/ADR-002-runtime-agent.md`) is required before
   the code changes: `fussion-reviewer` and `CLAUDE.md` section 5 currently enforce the old
   split, and reversing it without the ADR violates the repo's own contract.
2. **Plane question, to be decided in ADR-002.** Either (a) the runtime gets its **own**
   bounded loop and tool registry, keeping the runtime/engineering separation (recommended);
   or (b) the runtime uses the harness directly, collapsing the two-plane split. Option (a)
   preserves ADR-001's latency and ownership reasoning while still giving the runtime tools.
3. **Accepted tradeoff.** A loop on the high-volume path adds tool round-trips, tokens, and
   non-determinism. Mitigate with a bounded loop, a small per-org budget, tool invocation
   only when warranted, and streaming preserved.
4. **Safety is load-bearing.** Org scoping exists (`TenantContext` is frozen from
   public-key plus origin; write tools require a human `ApprovedPlan`). Because the runtime
   now *acts*, the tool gateway plus the per-org policy (L1 `OrgAgentPolicy`) must ship
   **before any write tool** does: read tools auto-authorised, writes gated.

## 2. Level L0 — Platform core (shared, versioned, slow-moving)

State: substantially built (see section 1). Build items:

- Runtime tool seam (**per ADR-002, now the primary L0 item**): `CustomerAssistant` currently
  **refuses any declared tools** and `app/runtime` may not import `app/agents`/`app/harness`.
  Build the runtime's own bounded loop and tool registry so the shared runtime agent can act
  per org. Effort: 5–8 days (the loop, registry, capability checks, budget, streaming
  preservation). Files: new `backend/app/runtime/tools.py`, `backend/app/runtime/loop.py`,
  extend `backend/app/runtime/assistant.py` (drop the tools-refused guard), update the
  `fussion-reviewer` rule, tests. Requires ADR-002 first.
- Channel adapter interface (platform-level): one ingress contract (normalise inbound message to tenant context plus text) and one egress contract (template check, policy check, send, log). Effort: 3–4 days. Files: new `backend/app/channels/` package with `base.py`, `registry.py`.
- Skill spec versioning: skills exist; add spec version plus per-org enablement flags so Tenant #2 never inherits Tenant #1's skills by default. Effort: 2 days. Files: `backend/app/skills/loader.py`, seeds.

## 3. Level L1 — Org-scoped execution claims (the missing middle)

State: org identity exists everywhere (`ExecutionContext`, `AgentRun`, `TenantContext`) but there is **no per-org execution policy object**. Build it:

- New model `OrgAgentPolicy` (migration 0031): `organization_id`, allowed colleague agents (name plus version pins), per-agent run budgets, approval thresholds (amounts and action kinds needing human sign-off), autonomy tier (`inform` or `commit`), channel allowlist, daily spend cap. Effort: 1 day for model plus migration plus schemas.
- Enforcement in the harness: `ExecutionContext` loads the org policy; the harness refuses unlisted agents and over-budget runs before the first model call; the tool gateway checks the policy on every write tool in addition to `ApprovedPlan`. Effort: 2–3 days. Files: `backend/app/harness/context.py`, `backend/app/harness/loop.py`, `backend/app/tools/gateway.py`.
- Per-org runtime config resolution: extend `resolve_customer_assistant` to merge platform instructions (immutable) with the org's `Assistant.system_instructions`, tone, escalation rules, and policy thresholds from `OrgAgentPolicy`. Effort: 2 days. Files: `backend/app/runtime/assistant.py`, `backend/app/models/assistant.py` (migration 0032 if new columns).
- Admin endpoints: CRUD for `OrgAgentPolicy` under org RBAC (managers only). Effort: 1–2 days. Files: new endpoint module, schemas, tests.

K Hotels relevance: autonomy tier starts at `inform`; thresholds say quotes and availability claims need approval; WhatsApp plus Gmail allowed, SMS capped.

## 4. Level L2 — Colleague agents (internal, per-org execution)

State: `website_analyst` and `coding_agent` run through the harness today. For K Hotels operations, add tenant-task colleagues, each a new `AgentDefinition` plus registration line (no core edits):

- `lead_qualifier` 1.0.0: structured lead extraction from any channel transcript; output schema is the lead record; budget small. Effort: 2–3 days.
- `followup_drafter` 1.0.0: timed nudge drafts from stalled qualified leads; template-checked; never sends (send is a commit-tier tool needing approval). Effort: 2–3 days.
- `reservation_parser` 1.0.0: Booking.com email to reservation record; deterministic-first with model fallback; output schema is the reservation record. Effort: 3–4 days.
- `knowledge_curator` 1.0.0 (later): stale-rate detection and re-chunk proposals on knowledge updates; drafts only. Effort: 3 days, deferrable past MVP.

Each runs with the org's `ExecutionContext`, so runs, costs, and tool calls attribute to K Hotels automatically.

### 4.1 Prerequisites before adding any colleague — from `standards-alignment.md`

`website_analyst` and `coding_agent` are **kept as colleagues, sequenced through the pipeline
with shared task state** — not upgraded into collaborating agents. That matches the *"shared
tasks, context"* shape without importing direct agent-to-agent messaging and the ASI07
controls it would require. **No change to the arrangement.**

What must be fixed first is **eval coverage asymmetry**:

| Gap | Why it blocks a new colleague |
|---|---|
| **G6** — `coding_agent` has no eval cases | A new colleague inherits an assurance model where the *existing* write-capable agent is untested |
| **G8** — live coding-agent path untested | `pipeline.py:202` disables the agent when `APP_ENV == "test"`; new colleagues added through the same assembly inherit the blind spot |
| **G7** — `approved_by` can be an organisation | Any colleague that writes inherits an approval record that does not reliably identify a human |
| **§5.2 ASI01** — repository content unfenced | Every colleague that reads tenant content needs the shared `fence_untrusted()` helper first |

Sequence: **G6 and G8 → G7 → ASI01 fence → new colleagues.**

## 5. Level L3 — Shared runtime agent (customer-facing, per-org resolution)

State: read-only answering with citations, per-project instructions, tenant resolution, rate limits. Under the new decision (ADR-002) this becomes a **bounded agent loop with tools, resolved per org**. Build items for K Hotels:

- **Runtime loop and tools** (L0 item above) enabling the runtime to call org-scoped tools.
- Lead-capture write path: visitor conversation may create a structured lead via a runtime
  tool, org-scoped, without granting any other write. Commit-tier (policy-gated). Effort: 2 days.
- Escalation path: "I don't know" and commitment requests create staff-queue items with the transcript attached. Effort: 2 days (queue model exists in jobs; needs the runtime call site).
- Per-org runtime tuning surface: tone, greeting, escalation rules, language handling — manager-editable, versioned so answers attribute to the config that produced them. Effort: 3 days across backend and Studio.
- Real embeddings swap (deterministic hash to provider embeddings) plus `uv run alembic` re-embed migration. Effort: 1 day. (Placeholder is demo-adequate; production is not.)

## 6. Level L4 — Channels (adapters bound per org)

Each adapter implements the L0 ingress/egress contracts and binds to the org's credentials (per-tenant encrypted secrets). Order by K Hotels value:

1. Gmail (read the 1,000-plus backlog and ongoing mail; send follow-ups): 4–5 days. Includes reservation-email parsing via the L2 `reservation_parser`.
2. WhatsApp Cloud API (primary guest channel): 4–5 days. Includes 24-hour window plus template enforcement in egress.
3. Web widget hardening (exists; needs lead-capture and escalation wiring): 2–3 days.
4. SMS via aggregator (confirmations and critical nudges only, daily cap): 2 days, last.

## 7. Level L5 — Staff surfaces (Studio wiring, currently mocked)

Backend memberships and RBAC exist; wire the mocked slices in this order, each following the established BFF pattern (typed client fn, React Query hook, replace mock, envelope errors):

1. Approval queue (commit-tier drafts with source attached; one-tap send, edit, reject): 4–5 days.
2. Knowledge editor (upload, list, delete, retrieval preview, version display): 3–4 days.
3. Integrations and analysis (repo connect, analysis trigger, run view): 3–5 days.
4. Metrics dashboard (response time, qualification and conversion rates, upsell attach, approval latency, cost per booking): 3–4 days.
5. Assistant config (tone, escalation rules, policy thresholds from L1): 2–3 days.
6. Runs plus agent runs (lists, event streams, fix the deliberately-broken diff endpoint first): 3–4 days.

## 8. Level L6 — Evals and observability per org

- Extend `backend/app/evals/` with K Hotels suites: rate-quote accuracy versus source feed, availability-claim grounding, escalation precision and recall, template compliance, PII-leak probes. Effort: 3–4 days.
- Per-org cost attribution (model plus channel spend against the L1 daily cap, alert on approach). Effort: 2 days.
- Audit-trail views (who approved what, which source, which policy version) for the risk assessment. Effort: 2 days.

## 9. Build order (dependencies, not dates)

- Phase A (platform): **ADR-002 written and accepted**; L0 channel contracts plus runtime
  loop and tool registry; L1 `OrgAgentPolicy` model, enforcement, admin endpoints.
- Phase B (colleagues): L2 `lead_qualifier`, `reservation_parser`; Gmail adapter (L4.1).
- Phase C (runtime plus staff): L3 lead-capture and escalation; L5 approval queue and knowledge editor (L5.1, L5.2).
- Phase D (reach): WhatsApp adapter (L4.2); L2 `followup_drafter`; follow-up engine; L5 metrics (L5.4).
- Phase E (proof): L6 evals and attribution; widget hardening (L4.3); SMS (L4.4); real embeddings; L5 remaining slices.

No phase starts without the eval or verification gate of the previous one passing (see section 10).

## 10. Verification gates per level

| Level | Gate | Command or check |
|---|---|---|
| L0 | contracts compile; runtime loop bounded; writes policy-gated; undeclared tools still refused | `uv run pytest backend/tests/test_tool_gateway.py backend/tests/test_runtime* -q` plus new `test_runtime_loop.py` |
| L1 | unlisted agent refused; over-budget run refused pre-call; write tool without policy fails | new `test_org_agent_policy.py` green |
| L2 | each colleague's output validates against its schema; fabricated-commit test refused | per-agent tests plus harness tests green |
| L3 | unknown question says so with no citation fabrication; lead write org-scoped | runtime chat tests green; manual probe script |
| L4 | template/window/cap violations blocked in egress with log lines | adapter tests with fake providers green |
| L5 | every wired slice works against the real backend with backend envelope errors surfaced | `pnpm build` plus slice checklists in frontend docs |
| L6 | quote accuracy and grounding suites pass before any autonomy-tier raise | `uv run python -m app.evals.runner` report attached to the change |

## 11. Known hazards (do not fix unless assigned)

- SSE pool leak in `studio_events.py` (holds a session per connection).
- `GET /runs/{id}/diff` deliberately raises 500; serve a persisted change set, do not re-derive.
- No real sandbox; nothing executes customer code.
- Retired layers (migrations 0007–0008 and planner/adapter modules) must not be extended.
- README and `CLAUDE.md` section 2 understate implemented features; trust code and history.
