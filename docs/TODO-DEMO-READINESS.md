# TODO: Demo Readiness

> Consolidated from architecture review. Three workstreams to reach an end-to-end demo.
>
> **Companion:** `TODO-INTEGRATION.md` — the L0–L6 build plan for org-scoped agent
> execution (colleague agents + shared runtime agent, per-org policy, channels, evals).
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

> **Status re-verified 2026-10-10: also partly stale.** Three of the five rows are already
> done — see the correction table below.

**Current:** Runs inside backend via ARQ workers; no public API.
**Target:** Public API so frontend (and external clients) can start/inspect agent runs.

| Task | Location | Effort |
|---|---|---|
| ~~Public Pydantic schemas~~ | **done** — `app/schemas/agent_run.py` (`AgentRunSummaryRead`, `AgentRunRead`) | done |
| ~~`GET` agent-run endpoints~~ | **done** — `app/api/v1/endpoints/agent_runs.py` exposes list, get-by-id (+ tool log), project usage, org budget | done |
| ~~AuthZ: org-member scoping~~ | **done** — `app/core/permissions.py` exists and is wired | done |
| **`POST /agent-runs`** — nothing can *start* a run over HTTP | `app/api/v1/endpoints/agent_runs.py` | 1 day |
| **`GET /agent-runs/{id}/events`** — no SSE stream of a live run | new, mirroring `studio_events.py` | 1 day |
| Rate limits / budgets per org | `app/core/rate_limit.py` + `app/jobs/queue.py` | 1 day |
| Frontend: replace mock agent runs | `frontend/src/lib/api/resources.ts`, hooks, components | 2–3 days |

The real gap is narrower than "build the agent API": reads already exist. What is missing is
the **write** path (start a run) and **streaming**. Until those land, runs are only
worker-triggered — which is exactly what §4 below assumes, so the demo path is unaffected.

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
| **Agent Runs** | Depends on #2 above | Run list, event stream, logs | 2–3 days |
| **Usage / Budget / Observability** | Metrics endpoints, SSE activity feed | Dashboard, charts, live activity | 2–3 days |

**Pattern per slice:**
1. BFF route already catches all `/api/backend/*` → no new Next.js routes needed
2. Add typed client fn in `frontend/src/lib/api/resources.ts`
3. Add React Query hook in `frontend/src/lib/api/hooks.ts`
4. Replace mock data in page/component
5. Error handling via existing envelope parser

---

## 4. Shortest path to end-to-end demo (2–3 weeks)

1. **Keep deterministic embeddings** — placeholder is fine for UI flow
2. **Trigger agent runs from existing ARQ workers** — no new API needed
3. **Wire these 4 frontend slices** (in order):
   - Integrations → Analysis (repo connect + analysis run)
   - Knowledge Base (upload + retrieval preview)
   - Assistant Config (config + widget preview)
   - Runs (list + diff + PR link — requires fixing `/runs/{id}/diff` 500)
4. **Point embed snippet** at `app/runtime/widget/` public route

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
