# TODO: Demo Readiness

> Consolidated from architecture review. Three workstreams to reach an end-to-end demo.
>
> **Companions:** `TODO-INTEGRATION.md` — the L0–L6 build plan for org-scoped agent
> execution. `TODO-KHOTELS-EVOLUTION.md` — what K Hotels needs on top of capabilities that
> already exist, and which L0/L1/L3 rows this framing supersedes.
> This document is the shorter "what is left before we can demo it" list.

## 1. Embeddings: deterministic hash → real model embeddings

> **Status: COMPLETE (2026-10-10).** Verified end to end against live Gemini embeddings.
> Only the optional quality work below remains.

**What was already true before this task** (the original plan was written against an older
snapshot and was wrong on three of its four rows):

- **Factory already wired.** `app/core/config.py` already defaults to
  `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_MODEL=gemini-embedding-001`,
  `EMBEDDING_DIMENSION=768`. `build_default_embedding_provider()` is called at KB creation
  (`app/api/deps.py:274`); `validate_embedding_configuration()` runs at startup
  (`app/main.py:90`).
- **`GeminiEmbeddingProvider` is complete**, not a stub — batched at 100, unit-normalised.
- **No re-embed migration is needed.** `knowledge_chunks.embedding` is an *unconstrained*
  `vector` (migrations 0027/0030), so the 384 → 768 dimension change needs no DDL.
- **The deterministic test assertions are correct as written.** `tests/conftest.py` pins
  `EMBEDDING_PROVIDER=deterministic` so the suite never calls a paid API. Do not "fix" this.

**What was actually done:**

1. `backend/.env` — set `EMBEDDING_API_KEY` (gitignored and untracked; never committed).
2. Seeded the empty database: org → project → knowledge base → document.
3. **Fixed a real defect in `scripts/seed_knowledge.py`.** It stored the whole document as a
   single 1052-character chunk, blending pricing / streaming / sandboxing / framework-detection
   into one vector. That compressed every score into a 0.42–0.56 band and made retrieval look
   far worse than it is. It now runs the document through the real `extract_and_chunk_markdown`
   (3 chunks), batch-embeds, and clears prior chunks so re-running is idempotent.

**Verification** — paraphrases sharing no literal tokens with the source document:

| Query | score | @ threshold 0.55 |
|---|---|---|
| "What does the premium tier cost per month?" | 0.5593 | 1 match |
| "how much do customers pay to go live" | 0.5893 | 1 match |
| "how do you figure out what web technology a site uses" | 0.5703 | 1 match |
| "does the system touch production code directly" | 0.6520 | 3 matches |
| *control:* "what is the wifi password for guest rooms" | 0.4489 | **0 matches** |
| *control:* "when does the breakfast buffet open" | 0.4241 | **0 matches** |

Paraphrases retrieve; irrelevant queries are gated out at `score_threshold=0.55`.

**Remaining optional quality work (not required for demo):**

| Task | Location | Effort |
|---|---|---|
| Retrieval-quality eval | New case type in `app/evals/` — only the engineering agent is evaluated today | 1 day |
| Hybrid retrieval / rerank | `app/services/knowledge/retrieval.py` is vector-only: no BM25 lexical arm, no reranker | 2–3 days |

**Note:** A practical threshold for this corpus is **0.55**. Below ~0.50 the controls start
leaking through; above ~0.65 recall degrades. Tune against a real corpus before trusting it.

---

## 2. Agent/harness/tool layer: internal → API-exposed

> **Status re-verified 2026-10-11: NARROWED. Deferred in favour of `POST /{run_id}/retry`.**
> Three of the five rows were already done, and an assessment of the remaining two found
> **no caller for either**. See the assessment below before starting any work here.

**Original scope:** Runs inside backend via ARQ workers; no public API.
**Revised scope:** one endpoint — retry a classified failure. Nothing else is justified yet.

### Assessment (2026-10-11)

The two proposed endpoints add almost nothing to the current state:

| Proposed | Verdict |
|---|---|
| `POST /agent-runs` — start a run by name/version | **No caller.** The Studio triggers work through `website-integrations/analyze`; nothing wants to start an arbitrary agent by hand |
| `GET /agent-runs/{id}/events` — per-run SSE | **Duplicates what exists.** A project-wide SSE stream already ships at `events/stream` (`studio_events.py`), and the frontend already consumes it via `src/lib/api/use-project-events.ts:33` |

Supporting evidence:

- **The frontend has zero references to `agent-runs`** — not in `resources.ts`, not in
  `hooks.ts`, not in `mock.ts`. These endpoints have never had a consumer.
- **Runs are already triggered:** `resources.ts:188` → `website-integrations/analyze` →
  ARQ job → harness. Job status polling already exists at `resources.ts:208`.
- **K Hotels needs none of it.** The runtime uses `ModelGateway` and never touches the
  harness — and per `TODO-KHOTELS-EVOLUTION.md` §1, that stays true.
- The module docstring (`agent_runs.py:1`) says *"Read-only agent-run and model-usage
  endpoints"* — read-only is deliberate, not an oversight.

### The real gap: FR-100 has no endpoint

The data model already anticipates retry; the API just never offered it:

- `app/models/agent_run.py:78` — `attempt` counter, **which nothing increments**
- `app/models/agent_run.py:39-40` — `FailureClass`, and FR-100: *"every failure is
  classified, and the class decides the response"*

An `AgentRun` can fail, get classified, and sit in the database with **no way to retry it**
short of re-triggering the entire pipeline from the top. That is the actual defect, and it is
about half a day, not two days.

### Revised task

| Task | Location | Effort |
|---|---|---|
| `POST /agent-runs/{run_id}/retry` — read `failure_class` to decide whether retry is permitted (FR-100 working as documented), increment `attempt`, re-enqueue the same agent + version + `prompt_hash`, return the new run id | `app/api/v1/endpoints/agent_runs.py` | half day |
| ~~`POST /agent-runs`~~ | deferred — no caller | — |
| ~~`GET /agent-runs/{id}/events`~~ | deferred — duplicates `events/stream` | — |

**Callers:** the Studio Runs page — which is itself unwired and belongs to §3. Building the
retry endpoint first is defensible because it closes a documented requirement against columns
that already exist; the UI can follow.

**Original rows, for the record:**

| Task | Location | Effort |
|---|---|---|
| ~~Public Pydantic schemas~~ | **done** — `app/schemas/agent_run.py` | done |
| ~~`GET` agent-run endpoints~~ | **done** — list, get-by-id (+ tool log), usage, org budget | done |
| ~~AuthZ: org-member scoping~~ | **done** — `app/core/permissions.py` | done |
| Rate limits / budgets per org | **partly done** — `ModelGateway` already enforces per-org spend; `agent_runs.py:151` exposes `/usage/budget`. Confirm before scheduling | verify |

---

## 3. Frontend: mocked slices → real backend wiring

**Current:** Only Auth / Organizations / Projects are wired. Everything else uses `src/lib/api/mock.ts`.

| Slice | Backend endpoints | Frontend work | Est. |
|---|---|---|---|
| **Integrations** | `GET/POST /integrations`, GitHub App install, `POST /analysis` | Wire integration list/create, install flow, analysis trigger | 3–5 days |
| **Repository / Analysis** | `POST /repositories`, `POST /snapshots`, async analysis (202 + SSE) | Repo connect, snapshot, analysis progress UI | 3–5 days |
| **Knowledge Base** | Upload, list, delete, retrieval preview | Upload UI, list, deletion, retrieval test panel | 3–4 days |
| **Assistant Config** | Config CRUD, widget preview, allowed origins | Config editor, preview iframe, origins manager | 3–4 days |
| **Runs / Integration Runs** | `GET /runs`, `GET /runs/{id}/diff` (currently 500), PR link | Run list, diff viewer (fix backend first), PR button | 2–3 days |
| **Agent Runs** | `GET /agent-runs`, `GET /agent-runs/{id}`, `/usage`, `/usage/budget` — **all already exist**. Retry from §2 | Run list, run detail + tool log, retry button. **No new event stream** — reuse `events/stream` | 2 days |
| **Usage / Budget / Observability** | Metrics endpoints, SSE activity feed | Dashboard, charts, live activity | 2–3 days |

**Pattern per slice:**
1. BFF route already catches all `/api/backend/*` → no new Next.js routes needed
2. Add typed client fn in `frontend/src/lib/api/resources.ts`
3. Add React Query hook in `frontend/src/lib/api/hooks.ts`
4. Replace mock data in page/component
5. Error handling via existing envelope parser

---

## 4. Shortest path to end-to-end demo (2–3 weeks)

1. ~~**Keep deterministic embeddings**~~ — **done.** Real Gemini embeddings are live and
   verified (see §1). No longer a placeholder step.
2. **Trigger agent runs from existing ARQ workers** — no new API needed, and §2 is now
   narrowed to a single retry endpoint, so nothing on this path is blocked.
3. ~~**Set `MODEL_API_KEY`**~~ — **done 2026-10-11.** Same Gemini key serves both embeddings
   and `gemini-2.5-flash`. Verified via `POST /public/chat`: grounded answers with citations,
   correct refusals out of scope, multi-turn history threaded.
4. **Wire these 4 frontend slices** (in order):
   - Integrations → Analysis (repo connect + analysis run)
   - Knowledge Base (upload + retrieval preview)
   - Assistant Config (config + widget preview)
   - Runs (list + diff + PR link — requires fixing `/runs/{id}/diff` 500)
5. **Point embed snippet** at `app/runtime/widget/` public route

---

## 5. Known hazards (do not fix unless assigned)

| Hazard | Location | Note |
|---|---|---|
| SSE pool leak | `backend/app/api/v1/endpoints/studio_events.py` | Holds `AsyncSession` per connection |
| `/runs/{id}/diff` deliberately 500 | `backend/app/api/v1/endpoints/website_integrations.py` | Must serve persisted change set, not re-derive |
| No real sandbox | `backend/app/services/integration/sandbox.py` | Path-checked dir only |
| Retired layers present | Migrations 0007–0008, `contract.py`, `integration_planner.py`, etc. | Do not extend; retired in step C1 |
| Leaked dev secrets in history | Git history (rewritten 2026-09-12) | Rotate anything they protected |

---

## 6. File locations for quick reference

```
backend/
├── app/
│   ├── services/knowledge/embeddings.py          # embedding factory
│   ├── services/knowledge/embeddings_gemini.py   # real provider (exists)
│   ├── api/v1/endpoints/agent_runs.py            # TO CREATE
│   ├── schemas/agent.py                          # TO CREATE
│   ├── core/permissions.py
│   ├── core/rate_limit.py
│   └── jobs/queue.py
├── alembic/versions/                             # new migration for re-embed
└── tests/test_knowledge*.py

frontend/
├── src/
│   ├── lib/api/
│   │   ├── resources.ts       # client fns (add per slice)
│   │   ├── hooks.ts           # React Query hooks (add per slice)
│   │   └── mock.ts            # replace slice by slice
│   └── app/(app)/orgs/[orgSlug]/projects/[projectSlug]/
│       ├── integration/       # wire first
│       ├── knowledge/         # wire second
│       ├── assistant/         # wire third
│       └── runs/              # wire fourth
└── docs/
    ├── 02-auth-wiring.md
    └── 03-projects-wiring.md  # follow this pattern
```

---

*Generated from architecture review. Update as slices land. Companion to `TODO-INTEGRATION.md`.*
