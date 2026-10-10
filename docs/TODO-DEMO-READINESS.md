# TODO: Demo Readiness

> Consolidated from architecture review. Three workstreams to reach an end-to-end demo.
>
> **Companion:** `TODO-INTEGRATION.md` — the L0–L6 build plan for org-scoped agent
> execution (colleague agents + shared runtime agent, per-org policy, channels, evals).
> This document is the shorter "what is left before we can demo it" list.

## 1. Embeddings: deterministic hash → real model embeddings

**Current:** `DeterministicHashEmbeddingProvider` (lexical, no semantics)
**Target:** `GeminiEmbeddingProvider` (or other real provider) — already scaffolded.

| Task | Location | Effort |
|---|---|---|
| Wire real provider in factory | `backend/app/services/knowledge/embeddings.py` | 1h |
| Add config keys | `backend/.env.example` (already documented: `EMBEDDING_PROVIDER`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL_ID`) | — |
| Migration: re-embed existing chunks | New alembic revision: `ALTER COLUMN embedding TYPE vector USING (new_embedding::vector)` | 2h |
| Update tests asserting deterministic output | `backend/tests/test_knowledge.py`, `test_knowledge_e2e.py` | 2h |

**Note:** Can demo with placeholder; semantic quality only needed for production QA.

---

## 2. Agent/harness/tool layer: internal → API-exposed

**Current:** Runs inside backend via ARQ workers; no public API.
**Target:** Public API so frontend (and external clients) can start/inspect agent runs.

| Task | Location | Effort |
|---|---|---|
| Public Pydantic schemas | `backend/app/schemas/agent.py` (new) | 2h |
| API endpoints: `POST /agent-runs`, `GET /agent-runs/{id}`, `GET /agent-runs/{id}/events` (SSE) | `backend/app/api/v1/endpoints/agent_runs.py` (new) | 1 day |
| AuthZ: org-member scoping | `backend/app/core/permissions.py` | 4h |
| Rate limits / budgets per org | Extend `backend/app/core/rate_limit.py` + `app/jobs/queue.py` | 1 day |
| Frontend: replace mock agent runs | `frontend/src/lib/api/resources.ts`, hooks, components | 2–3 days |

**Decision point:** Does the demo need external agent API, or is internal worker-triggered
enough? If internal is fine, skip this entire workstream.

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
