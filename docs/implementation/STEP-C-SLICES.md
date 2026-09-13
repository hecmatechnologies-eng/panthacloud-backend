# Step C — Analyst, harness, tools, skills, evals

Step C from `docs/FEASIBILITY.md` §3, broken into slices. Propose no work outside the current
slice. Each slice declares its rigour tier per `CLAUDE.md` §9.0.

Deliverable: the engineering plane's first agent — `WebsiteAnalyst` running through a thin,
governed harness over read-only repository tools, with skill packages and an eval corpus from day
one. Requirement groups: B1 (harness), B3 (tools), B5 (skills), B6 (evals), FR-058–062 (project
memory). ADR-001: adopt Pydantic AI, imported only in `app/llm/adapters/`.

## Prerequisites and gates

Settled before this step:

- The verified step-A + B2–B6 work is committed to `main`; the leaked dev secrets were rewritten
  out of history (`git filter-repo`, 2026-09-12).
- The 05–08 decision (2026-09-12): **repurpose** the read/detection substrate, **retire** the
  contract/adapter/execution-plan layers. Executed in C1.

Still to arrange, each gating the slice that needs it:

| Gate | Needed by | Note |
|---|---|---|
| A repository-read source for the tools | C4 | `GitProvider` has `get_file_contents` but **no tree/search**; either add them or wrap the `WorkspaceManager` clone. C1 decides. |
| `pydantic_ai` installed | C5 | Not currently a dependency; ADR-001 confines it to `app/llm/adapters/`. |
| Agent Skills validator (`agentskills`, the console script of the `skills-ref` package) | C7 | FR-083b requires CI validation; the CLI is not installed. |
| Frontend widget-target fixtures | C9 | Existing `tests/fixtures/repositories/` are backend-shaped (Django/FastAPI/Express). |

## Slices

| # | Slice | Tier | Done when |
|---|---|---|---|
| C1 | Retire the 05–08 contract/adapter/execution-plan layers; extract the read/detection substrate | 2 | The retired models, endpoints, services, frontend tabs and tests are gone (a drop migration keeps the chain valid); `workspace`/`acquisition`/`inspection` and the detectors are reachable as the analyst's substrate; `upgrade → downgrade → upgrade` clean on SQLite and Postgres |
| C2 | `ExecutionContext` + `AgentRun` persistence + agent definition/registry | 1 | Context built only from trusted state; a run records agent version, prompt hash, model id + reported version, skill versions and the ordered tool-call log |
| C3 | Tool Protocol + registry + gateway | 1 | One choke point: authorize → execute → record; read auto-authorized, write requires an approved plan |
| C4 | Read-only repository tools (`read_tree`, `read_file`, `search_code`) | 1 | Offset/limit and an explicit truncation signal; actionable errors; scope resolved from `ExecutionContext` |
| C5 | Pydantic AI adapter + `AgentRunner` Protocol | 1 | Structured output validated (unparseable = failed step); `pydantic_ai` imported only in `app/llm/adapters/`; usage flows through the gateway |
| C6 | Harness loop + budget + authorization | 1 | One loop; per-run budgets (tool calls, tokens, wall clock, cost) declared and enforced, terminating on breach |
| C7 | Skills structure + 2 packages (`nextjs-app-router`, `generic-html`) | 2 | Agent Skills spec; `SKILL.md` under 5k tokens; progressive disclosure; `agentskills validate` passes in CI |
| C8 | `WebsiteAnalyst` + `WebsiteProfile` | 1 | Detects framework, router, app shell, entry points and design tokens, or returns `unsupported_reason`; `integration_candidates` is a ranked list |
| C9 | Eval corpus + runner | 1 | 5 fixtures (at least one refusal); assertions on structured fields; per-case and aggregate outcome, cost and wall time; gates C8 |
| C10 | Control-plane wiring + Studio surface | 1 | Framework, shell and integration point are auto-detected and persisted; no framework dropdown, no typed path |

## Notes

**Evals gate C8, not a later phase.** The corpus and runner are required from agent #1
(AGENT-ARCHITECTURE §12). C8 is not "done" until C9 is green against it.

**The eval runner uses the configured real provider and runs manually / pre-release.** CI must
never hit a paid API; unit tests and CI use the deterministic fake. This is the same split the
model and embedding planes already use.

**C1 keeps migrations 0007 and 0008 in place** for the chain's history and adds a new migration
that drops the retired tables — deleting an applied migration would break `upgrade head`.

**No `if framework ==` in core.** Framework knowledge lives in skill packages (AGENT-ARCHITECTURE
§6); adding a framework is a new folder, not an edit to planning, generation or validation.

**pgvector is not a step-C slice.** Full-scan cosine is adequate at a few hundred chunks
(`STEP-B-SLICES` Notes).

**Project memory (FR-058–062) is thin and derived** — fingerprinted by `commit_sha`, tenant-scoped,
fenced as data on read-back, purgeable. It lands within C2/C6 rather than as its own slice.
