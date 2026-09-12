# CLAUDE.md — Fussion Engineering Contract

Read this before touching anything. It is the operating contract for any AI or human
contributor working in this repository.

Principles reference: <https://github.com/webpro/programming-principles>
Architecture reference: `docs/architecture/AGENT-ARCHITECTURE.md`
Scope & requirements: `docs/requirements/MVP-REQUIREMENTS-V2.md` (supersedes Phase 2 §5–§10)
Agent layer decision: `docs/architecture/ADR-001-agent-layer.md`
**What is actually realistic: `docs/FEASIBILITY.md` — read this before planning work**
How to work here: `docs/DEVELOPMENT-WORKFLOW.md` · Tooling: `docs/CLAUDE-CODE-SETUP.md`

### Conditional reads — this file is a summary, not the whole contract

Only `CLAUDE.md` loads automatically. The documents below carry detail this file does not.
**Read the named document in full, before planning, when a slice touches its area:**

| Touching | Read first |
|---|---|
| `app/agents/` `app/harness/` `app/tools/` `app/llm/` `app/runtime/` `skills/` | `docs/architecture/AGENT-ARCHITECTURE.md` — agent contracts, budgets, memory tiers, tool standards, skill spec |
| anything introducing a model call or provider | `docs/architecture/ADR-001-agent-layer.md` |
| new scope, or an abstraction you cannot tie to an existing requirement | `docs/requirements/MVP-REQUIREMENTS-V2.md` — including the Part D YAGNI register |
| planning a phase or estimating effort | `docs/FEASIBILITY.md` |

§5 names the boundaries; it does not contain the contracts. Do not write an agent, tool,
skill or runtime module from this file alone.

---

## ⚠ Terminology — two different things are called "agent" here

Confusing these is an architectural error, not a wording slip.

| | **Development subagents** | **Fussion product agents** |
|---|---|---|
| Defined in | `.claude/agents/*.md` | `backend/app/agents/` |
| Run by | Claude Code, on a developer's machine | Fussion's own harness, in production |
| Work on | this repository | a *customer's* repository |
| Serve | Hecma engineers | Fussion tenants |
| Examples | `fussion-reviewer` | `WebsiteAnalyst`, `CodingAgent` |
| Ship to customers | never | yes |

**Rules**

- Fussion's product agents are **never** implemented using Claude Code's Task tool, its
  subagents, or the Claude Agent SDK. Fussion builds and owns its own harness because it
  must enforce its own multi-tenant authorization, budgets, audit and capability model.
- Nothing under `backend/app/` may import or depend on Claude Code, its SDK, or its
  subagent mechanism.
- Development subagents may read and review `backend/app/agents/`. They are not part of
  it.
- Conceptual overlap between the two harnesses is real and useful as inspiration. It is
  never an implementation shortcut.

When this file says "agent" without qualification, it means a **Fussion product agent**.

---

## 1. What Fussion is

An **AI Integration Engineer Platform**. A business connects its website repository and
uploads its company knowledge; Fussion analyses the repo, plans an integration, modifies
code on an isolated branch, validates it, and opens a pull request that installs a
knowledge-grounded AI assistant on that website.

**The integration work is the product.** If a change makes Fussion more like a chatbot
builder that hands the user an embed script, it is moving in the wrong direction.

---

## 2. Honest current state — do not assume more than this exists

Verify before you build on any of it.

**`GitHubProvider` is wired in (2026-09-12). The running app talks to real repositories.**
`configure_git_provider()` runs from `lifespan`, so a Studio run now reads the customer's real
widget target at a pinned commit, commits to an integration branch, and opens a pull request —
provided the integration carries a GitHub token that can read the repository. Runs still fail
closed, with a reason, whenever the target is missing, protected, or has no safe insertion point.

Tests are unaffected: `lifespan` does not run under `ASGITransport`, so the suite uses
`MockGitProvider`. Any process that runs neither — a future worker — gets a provider whose every
method raises, rather than the mock's fabricated commit SHA and dead pull-request URL (§4.10).

**Built and working**

- Control plane: users, organizations, memberships, RBAC, JWT auth
- Projects, integrations, repositories, repository snapshots
- Knowledge base: upload, extract (PDF/MD/TXT), chunk, embed, retrieve
- Assistant configuration + widget preview
- Studio frontend: stage model, navigation, theming, SSE activity feed
- Backend tests, Ruff clean — but see §8: the suite does not run from `backend/` on a
  machine whose `backend/.env` points at Postgres

**NOT built — do not write code that assumes these exist**

- **No LLM anywhere.** No model SDK, no provider, no gateway, no API key handling.
- **No agents, no harness, no orchestrator, no tool registry.**
- **No runtime plane.** A website integration now *has* a public key and registered
  allowed origins (step B1), and both are managed through the authenticated control
  plane — but **nothing reads or enforces either yet**. No tenant resolver, no visitor
  session, no `Conversation`/`Message`, no streaming chat, no rate limiting. Every route
  today still sits behind `/organizations/{org_id}/...` auth.
- **No real sandbox.** `SandboxManager` is a path-checked directory. It provides no
  process, filesystem, or network isolation. Nothing executes customer code today.
- **No pgvector, no Redis, no object storage, no job queue, no workers.**
- **No repository analysis feeding the integration.** The user picks the framework from
  a dropdown and types the target path by hand.
- **No memory layer.** No project memory, no conversation memory, no run history beyond
  `IntegrationRun` status columns.
- **No evaluation harness.** There is no way to tell whether a prompt or model change
  made the system better or worse.

**Embeddings are a placeholder.** `DeterministicHashEmbeddingProvider` hashes words and
character n-grams. It is lexical fuzzy matching, not semantics. It must be replaced
before any real question-answering ships.

---

## 3. Known hazards — fix before building on top

1. **Resolved (branch `fix/layout-overwrite`) — `pipeline.py` overwrote customer files.**
   What now holds, and its limits:
   - The pipeline pins the default branch's head SHA, reads the real widget target *at that
     SHA*, and creates the integration branch *from that SHA* (recorded as
     `plan_summary.base_sha`). A customer commit landing mid-run is never silently
     reverted: git merges it cleanly if it does not overlap Fussion's change, and the PR
     conflicts if it does.
   - A missing target is refused (`IntegrationRefusedError`, HTTP 422), never created.
   - `StaticValidator` requires every modified file's original, and rejects insertions,
     deletions and in-line rewrites of content outside Fussion-managed blocks — **unless the
     edit is itself wrapped in Fussion marker text**, which the validator currently treats
     as a managed block wherever it appears (see the blockers below).
   - Whitespace is ignored when comparing, and whitespace can change meaning: `return (` →
     `return\n(` makes the layout return `undefined` and render a blank page, and
     `"admin hidden"` → `"adminhidden"` silently drops a class. Neither is detected.
   - `generate_artifacts` has no stub fallback; it cannot build a customer file without the
     real content.

2. **The leaked dev secrets are out of source; they are still in git history.**
   `SECRET_DEV_ENCRYPTION_KEY` and `JWT_DEV_SECRET` are gone from `app/core/config.py`
   (2026-09-12). Development keys are now generated per installation into a gitignored
   `.dev-secrets.json` (`app/core/dev_secrets.py`), or supplied by the environment; production
   still refuses to start without real values, and now rejects the two leaked ones by hash.

   **Still a hard blocker on first push:** both values entered git history in the baseline
   commit `f4027e0` (2026-09-11), which is now in `main`. Before adding any remote, either
   rewrite history or treat both as compromised and rotate anything they protected. **Every
   commit added on top makes the rewrite larger.**

   Consequence to expect locally: a development database still holding GitHub tokens encrypted
   under the old hardcoded key cannot decrypt them. The token must be re-entered — or set
   `SECRET_ENCRYPTION_KEY` to the old value in `backend/.env` for continuity, accepting that it
   is a compromised key. A failed decryption is logged rather than silently ignored.

3. **Resolved (2026-09-12) — generated files follow the project's source root.**
   `source_root_for()` derives the root from the widget target (`src/app/layout.tsx` → `src/`),
   generated files are written beside that tree, and the imports between them are **relative**,
   so nothing depends on a `@/` alias Fussion has not read. A target outside any `app/` or
   `pages/` tree is refused, because the source root cannot be determined.

4. **Resolved (2026-09-12) — one plan, one numbering scheme.** Work is identified as a
   **step and slice**: steps A–D from `docs/FEASIBILITY.md` §3, sliced per step in
   `docs/implementation/STEP-<X>-SLICES.md` — "step B, slice B1". Use nothing else.
   - The 19-phase `MVP-IMPLEMENTATION-ROADMAP.md` is archived under `docs/archive/` and is
     not a plan. Do not cite its phase numbers.
   - `ANTIGRAVITY-PHASE-TRACKER.md` keeps its `01`–`12`/`A`/`B`/`B.1` entries as the
     **historical record of work already done**. Those numbers are never used for new work,
     and never appear in a plan, commit message or tracker entry for it. Note the trap they
     set: the tracker's legacy "Phase B.1" is frontend authentication, and has nothing to do
     with step B slice B1.

5. **Orphaned subsystem.** `repository_snapshots`, `discovery`, `contracts`,
   `integration_adapters`, `execution_plans` (migrations 0004–0008) are referenced by
   **nothing** in the MVP integration path. Decision pending: repurpose the deterministic
   analysis for app-shell/design detection, or retire it. Do not extend it meanwhile.

6. **SSE leak.** `studio_events.py` holds an `AsyncSession` open for the life of each
   connection while polling every second. It will exhaust the pool.

7. **`GET /runs/{id}/diff` is deliberately broken.** `get_run_diff` in
   `website_integrations.py` re-derived the diff from the *current* assistant config and a
   hardcoded stub layout, so the Studio showed a file the PR never contained. The stub is
   gone and `generate_artifacts` now requires the real content, so the endpoint raises
   `TypeError` (500) — left that way on purpose rather than papered over. Fix: persist the
   generated change set on the `IntegrationRun` and serve that; do not re-derive it.

### Remaining step-A items, and what each one blocks

Step A is "truth & safety" (`docs/FEASIBILITY.md` §3). These are what is left of it. Each has a
trigger rather than a date: do it before the thing it blocks, not "eventually". Four items with
named triggers do not need a document of their own.

| Item | Hazard | Trigger — do it before | Why then |
|---|---|---|---|
| ~~Remove the leaked dev secrets from source~~ | §3.2 | ~~B2~~ | **Done 2026-09-12.** The history rewrite remains, and still grows with every commit. |
| ~~`@/` alias vs `src/` layout~~ | §3.3 | ~~B8~~ | **Done 2026-09-12.** Brought forward: wiring the provider made this the slice whose output has to build in a customer's repo. |
| Phases 05–08: repurpose or retire | §3.5 | **step C** | Step C builds the analyst. Either its deterministic detection reuses `discovery.py` or that subsystem goes; deciding after C is built means building it twice. |
| `SandboxManager` rename + `SandboxProvider` Protocol | §2 ("no real sandbox") | **with B5 or later** | Nothing executes customer code yet, and the name claims otherwise. The Protocol is cheap once a second implementation is plausible; before that it is speculative. |

### Safety gates that now hold — all five wiring blockers closed (2026-09-12)

The gate list that stood here is empty. What replaced each item, and the limit that remains:

- **FR-096 protected paths are enforced at three points** (`app/core/protected_paths.py`):
  the create/update schema refuses a protected `widget_target_path` (422 at configuration
  time), the pipeline refuses one before reading anything, and `StaticValidator` rejects any
  protected path among generated *or* declared files. Patterns are case-insensitive and
  include `middleware.ts`, `.npmrc`, `.envrc`, CI directories and deployment config.
- **Marker-pair discipline** (`validation.py`): a file is compared against its own framework
  family only, each marker may appear once, and each must stand alone on its line. If
  discipline fails the customer-content comparison is **skipped**, never trusted. The families
  and the suffix map live in `artifacts.py` beside the patchers that emit them.
- **`GET /plan`** resolves the branch head, then reads the target at that SHA, so a private
  repository, a wrong default branch and a bad token each report their real cause.
- **`create_branch(..., base_sha)` is required** across the Protocol and both providers.
- **FR-097 generated-code scan exists** (`code_scan.py`): created files in full, and managed-block
  content for modified files. Foreign origins include protocol-relative, `data:` and
  `javascript:` URLs, and resource attributes beyond `<script src>`.
- **The patchers are deliberately conservative: exactly one candidate, or refuse.** Text matching
  cannot distinguish `</body>` the element from `</body>` inside a string or a comment, so a file
  containing more than one candidate is refused rather than guessed at, as is a layout with none
  (one that delegates its shell), a React target outside an `app/`/`pages/` tree, and a static
  target that is not an HTML file. The import block is inserted *below* any `'use client'`
  directive. Every one of these produced a file that did not compile, inside a managed block the
  validator does not inspect — so refusing is the only honest answer until a build check exists.
- **Generated code is scanned; the tenant's own configuration is not.** Config values are fenced
  (`CONFIG_BEGIN`/`CONFIG_END`) and checked only for executable schemes. Scanning them as code
  meant any tenant who set an avatar URL could never obtain a pull request.
- **The pull-request body states what Fussion did *not* do** — no dependency install, no
  type-check, no build — rather than claiming "Sandbox validation: PASSED" (FEASIBILITY §4).

**Remaining limits, attached to what makes them reachable:**

| Limit | Gate on |
|---|---|
| The scan cannot judge whether managed-block content is *plausible*, only whether it is malicious | step-D CodingAgent: agent-authored blocks need a build or type check, not just a scan |
| Computed network destinations are flagged but not resolved; `postMessage`, dynamic imports and CSS `url()` are not covered | step-D CodingAgent |
| A whitespace-only change is still invisible to the comparison (§3.1's known limit) | step-D CodingAgent — the deterministic patcher cannot produce one |
| A failed run leaves its integration branch behind (FR-106); nothing deletes it | step-D resilience, or the job queue — needs `delete_branch` and verified teardown |
| `_patch_preserving_line_endings` normalises a mixed-ending file, so the PR touches every line | B8, when a real widget makes diff size matter |
| **The conservative patchers refuse real-world layouts** a person would integrate by hand — anything with a duplicated candidate tag, a delegated shell, or an unconventional target. This is the intended trade while nothing verifies output | step C's `WebsiteAnalyst` (ranked candidates, a human choosing) and step D's build check |
| `GET /runs/{id}/diff` still raises (§3.7), and it is now reached on **every successful run** rather than never | its own slice — persist the change set on `IntegrationRun`; this is the Studio's change-inspection surface |

---

## 4. Non-negotiable invariants

Violating any of these is a blocking review failure, regardless of test results.

1. **Tenancy is resolved by infrastructure before the model sees anything.**
   An LLM never decides, infers, or supplies a tenant identifier. Every tool call and
   every query derives its scope from a trusted `ExecutionContext` constructed by the
   platform.

2. **The LLM never holds a credential.** Not a GitHub token, not a database URL, not an
   API key. It requests a capability; the tool layer resolves the credential.

3. **The LLM never decides its own permissions.** Authorization happens outside the
   model, before the tool executes.

4. **Agents reach Fussion only through contracts and gateways.** An agent module that
   imports a SQLAlchemy model, a repository class, or `httpx` directly is wrong by
   construction. No `database.py`, no `github_client.py` inside `app/agents/`.

5. **Untrusted content is data, never instruction.** Repository files, uploaded
   documents, tool output, retrieved chunks, and visitor messages are fenced in the
   context, never concatenated into the instruction region.

6. **No customer code executes on the control plane.** Ever. Until a container-backed
   `SandboxProvider` exists, `run()` raises.

7. **Nothing merges to a customer's default branch automatically.** Branch + PR + human
   approval.

8. **Never modify a customer file without first reading its real contents.**

9. **Protected paths are absolute.** No approved plan, configuration, or user-supplied
   path may cause a write to `.env*`, `credentials/`, `.github/workflows/`,
   `infrastructure/`, deployment configuration, authentication, payment, or database
   schema files. (Phase 7 §7.13, AGENT-ARCHITECTURE §11 control 3, FR-096.)

10. **Production fails loudly; it never falls back.** PostgreSQL is the system of record, and
    the SQLite fallback is for local development and test only. A missing `DATABASE_URL`, a
    SQLite URL, or a missing, placeholder or known-compromised secret raises at startup rather
    than degrading to something that appears to work. Development keys are generated only for
    explicitly named development environments — never for an unrecognised `APP_ENV`.

11. **The public surface is configuration-driven, and says nothing about internals.** CORS
    comes from an integration's registered allowed origins; `allow_origins=["*"]` is never
    used in production. Public health endpoints return operational status only — no database
    engine, version, latency or internal topology.
    *(Both carried from `ANTIGRAVITY-PROJECT-RULES.md` §4 when it was archived, 2026-09-12.
    §4.11 binds the B2 tenant resolver and the B4 public endpoint.)*

---

## 5. Architecture boundaries

```
Studio (Next.js)
      ↓
Control Plane      identity, tenancy, projects, policy, approvals, secrets
      ↓
Orchestration      owns workflow state — the LLM does not
      ↓
Agent Harness      context, tools, authorization, budget, tracing
      ↓
Agents             thin declarations: instructions + tools + output schema
      ↓
Tool Gateway       single choke point: authorize → execute → record
      ↓
Execution          workspace today; container sandbox later
```

**Import rules**

- `app/agents/` may import `app/harness/` contracts only.
- `app/harness/` may import `app/tools/`, `app/llm/` **abstractions**, never concrete
  providers.
- Within the agent stack, `app/tools/` is the only layer that touches domain services, the
  database, GitHub, or the filesystem; `app/agents/` and `app/harness/` reach them only through
  it. The control plane, `app/services/`, the runtime plane (`app/runtime/`), and the model
  gateway's usage accounting (`app/llm/gateway.py`, per AGENT-ARCHITECTURE §2) access the database
  directly by design — this rule constrains the agent layer, not the platform.
- `app/runtime/` (visitor data plane) must not import `app/agents/` or engineering tools.
- `app/models/` is SQLAlchemy ORM. LLM provider code goes in `app/llm/`, never `models/`.

**Two planes, deliberately asymmetric.** The engineering agent runs a full loop with
tools, budgets, and approval gates. The visitor runtime is a single-turn pipeline:
resolve tenant → retrieve → assemble → stream. Do not force the runtime through the
agent loop; it has different volume, latency, and risk.

---

## 6. Principles, with Fussion-specific teeth

The full list lives at <https://github.com/webpro/programming-principles>. These are the
ones that bite hardest in this codebase — apply them concretely, not as slogans.

**YAGNI / Do The Simplest Thing.** The harness grows only as much as the agents in it
demand. One model provider until there is a reason for two. No MCP client until we cross
an ownership boundary. No workflow engine until a run actually needs to survive a
restart. Speculative abstraction is the failure mode this project is most exposed to.

**Encapsulate What Changes.** Framework-specific integration knowledge changes constantly
and belongs in `skills/integrations/<framework>/`, not in Python. Model providers,
sandbox backends, and vector stores change; each sits behind one Protocol.

**Open/Closed.** Adding a framework must mean adding a folder. Today it means editing an
enum, an Alembic migration, `planner.py`, `artifacts.py`, `validation.py`, a frontend
type union, and the tests. That is the OCP failure to eliminate.

**Single Responsibility.** `IntegrationPipeline.execute()` currently does credential
decryption, data fetching, planning, workspace allocation, generation, validation, branch
creation, commit, PR, audit, error handling, and cleanup in one ~200-line method. Split
into an orchestrator plus named, individually testable, individually resumable steps.

**Keep things DRY.** The assistant configuration is assembled in `pipeline.py` and
serialized again in two places in `artifacts.py`. One `AssistantBlueprint` DTO, one
serializer.

**Connascence.** Prefer connascence of name over position, and keep strong forms local.
`retrieval.py` hardcodes `dimension=384` at the call site — connascence of value across a
module boundary. Store the dimension on the knowledge base and resolve the provider from
it.

**Optimize for Deletion.** Every agent, tool, and skill must be removable by deleting its
folder and one registry line. If removing a capability requires touching the harness, the
boundary is wrong. This is also the test for the orphaned Phase 05–08 subsystem: if it
cannot be cleanly deleted, it is too entangled to keep ignoring.

**Dependency Inversion.** `GitProvider` and `EmbeddingProvider` are already correct —
copy that shape exactly for `ModelProvider`, `SandboxProvider`, `ToolProvider`.

**Liskov Substitution.** The deterministic test double and the real provider must be
genuinely interchangeable. If a test passes only with the fake, the abstraction is a lie.

**Command Query Separation.** Tools are explicitly typed read or write. Read tools are
auto-authorized; write tools require an approved plan and a granted capability. This is
not a style preference here — it is the authorization model.

**Minimise Coupling / Law of Demeter.** Agents talk to the gateway. The gateway talks to
tools. Tools talk to services. No reaching through.

**Hide Implementation Details.** An agent must not know whether GitHub is reached via
REST, a GitHub App, or an MCP server.

**Do not reinvent mature infrastructure.** No custom HTTP framework, ORM, database driver,
authentication primitive, task queue, validation library or logging framework. The agent
harness is the one deliberate exception, for the reason in the terminology section: Fussion
must own its own multi-tenant authorization, budgets, audit and capability model. That is an
argued exception, not a licence for others.

**Inspect before modifying.** Understand why existing code is there, and what depends on it,
before changing it. Preserve working behaviour unless there is a stated reason to change it —
the counterpart, for our own code, of §4.8 for a customer's.

**Boy Scout Rule.** Applies to the hazards in §3. If you are already in `pipeline.py`,
leave it better. Do not let §3 items age.

**Avoid Premature Optimization.** Retrieval currently full-scans every chunk in Python.
That is a correctness-adjacent scaling problem, not a micro-optimization — fix it with
pgvector when real embeddings land, not before.

**FIRST / Arrange-Act-Assert.** Model calls are mocked in unit tests; no test may hit a
paid API. The backend suite currently takes 164s — keep new tests fast and isolated.

---

## 7. Deterministic first, model for the gaps

The strongest cost, latency, and reliability lever in this system.

Reading `package.json`, detecting Next.js, locating `app/layout.tsx`, listing
dependencies — all deterministic. Doing it with an LLM is slower, costlier,
non-reproducible, and **less accurate**.

Use the model only where determinism genuinely fails: an unconventional app shell,
judging design and styling conventions, choosing an injection strategy for a repo
matching no template, diagnosing a build failure.

If you are about to add a model call, first answer: *why can't code do this?*

---

## 8. Commands

```bash
# Backend
cd backend
.venv/Scripts/ruff check app tests      # Windows
.venv/Scripts/pytest tests
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend
cd frontend
pnpm test
pnpm build
pnpm dev
```

`pnpm` is the only package manager for the frontend. `uv` manages the backend
environment.

**Test database caveat.** Settings load `.env` from the working directory. Running pytest
from `backend/` picks up `backend/.env`; if its `DATABASE_URL` is Postgres, every test
errors at setup (psycopg async cannot use Windows' Proactor event loop). Until the test
config stops inheriting `.env`, run from the repository root:
`backend/.venv/Scripts/pytest backend/tests`.

---

## 9. Definition of done

### 9.0 Rigour tier — decide this before starting, state it in the plan

Verification scales with **blast radius**, not with how interesting the problem is. Applying
maximum rigour everywhere is not caution; it is a different way of failing to ship —
see `docs/FEASIBILITY.md` §3 for the budget this has to fit inside.

| Tier | Applies when the change can | Gate |
|---|---|---|
| **1 — Maximum** | write to a customer repository · resolve tenancy · handle credentials · generate code that ships to a customer site · touch an agent, prompt, skill or model | red-first test, reviewer, iterate until the reviewer reports no defect reachable by the code as it runs |
| **2 — Standard** | change backend behaviour with no customer-repo, credential or cross-tenant path | tests + ruff + **one** reviewer pass; findings logged, fixed in-slice only if they are defects in what this slice built |
| **3 — Light** | only touch docs, tracker, fixtures, or the frontend | tests + ruff; no reviewer round |

**Stopping rule for Tier 1.** Commit when no finding describes a defect reachable by the
code as it currently runs. Findings that require a component which does not exist yet are
logged as gates on the component that would make them reachable — not fixed now. A
reviewer asked to find problems will always find problems; without this rule a slice never
lands.

**Tier 2 does not escalate to Tier 1 because the reviewer found something.** It escalates
only if a finding shows the change actually has Tier 1 reach.

### 9.1 Checklist

**Always**

- [ ] Ruff clean, full backend suite passing, `pnpm build` and `pnpm test` clean
- [ ] No invariant in §4 violated
- [ ] New capability is removable by deleting a folder and one registry line
- [ ] No new `if framework ==` branch in core code
- [ ] Tenancy derived from `ExecutionContext`, never from a model-supplied value
- [ ] Alembic migration verified `upgrade → downgrade → upgrade` on **both** SQLite **and** a
      scratch Postgres database the check creates and drops — never `fussion_db`:
      `backend/.venv/Scripts/python.exe backend/scripts/verify_migration.py`, plus
      `--seed backend/scripts/seeds/<revision>.py` whenever the migration backfills or alters
      existing rows (write that seed module; a backfill is not verified without pre-existing rows).
      SQLite is permissive about precisely what Postgres enforces: B1 shipped a value that
      overflowed a `String(255)` column, invisible on SQLite and a 500 on Postgres. Production is
      Postgres by contract (`config.py` refuses SQLite there), and pgvector will be Postgres-only.
- [ ] Cross-tenant access returns 404, not 403 (anti-enumeration)
- [ ] No secret in code, logs, prompts, commits, or browser storage
- [ ] `ANTIGRAVITY-PHASE-TRACKER.md` updated in the same commit as the work

**Additionally, when the change touches an agent, prompt, skill, tool or model**

- [ ] Eval suite run and green; new behaviour has a corpus case, including a refusal case
- [ ] Assertions are on structured output fields, not exact strings
- [ ] `AgentRun` records agent version, prompt hash, model id + provider-reported version,
      skill versions, and the ordered tool-call log
- [ ] Budget declared (tool calls, tokens, wall clock, cost) and enforced
- [ ] No test hits a paid API; the fake provider is genuinely substitutable

**Additionally, when the change adds or modifies a tool**

- [ ] Read/write classified; required capability declared
- [ ] Unbounded output paginated with an explicit truncation signal
- [ ] Errors are actionable and model-readable, not stack traces
- [ ] Description written for the model
- [ ] Scope resolved from `ExecutionContext`, never from tool arguments

**Additionally, when the change generates code that ships to a customer site**

- [ ] Every written path is declared in the approved plan
- [ ] Original file content was read before modification
- [ ] Generated output passes the security scan (no `eval`, no foreign script src, no
      undeclared network calls, no inline handlers)
- [ ] Protected paths untouched

**Additionally, when the change adds or reads memory**

- [ ] Written to the correct tier; no tier merging
- [ ] Project memory carries a `commit_sha` fingerprint and is treated as stale on
      mismatch
- [ ] Memory content is fenced as untrusted data in any prompt
- [ ] Purged when the owning repository or project is deleted
- [ ] No cross-tenant read path exists

---

## 10. Working agreements

- **Ask before scope expansion.** If a task requires touching a subsystem outside its
  stated boundary, stop and say so.
- **Never mark a phase complete in the tracker unless the code actually shipped**, and
  never without `fussion-reviewer` having passed it. The tracker has been wrong before:
  it said Phase 11 was pending while Phase 11 code was running in `pipeline.py`.
- **"Deviations: None" is almost always false.** If a phase genuinely had none, record
  what was checked to establish that.
- **Do not redesign backend architecture to make UI implementation easier.**
- **Do not introduce a third phase-numbering scheme.**
- **`pydantic_ai` is imported only in `app/llm/adapters/`.** Never in `app/agents/`,
  `app/harness/`, `app/tools/` or `app/runtime/` (ADR-001).

### The failure pattern to avoid

Phases 01–11 shipped in about two days, every one recorded as *COMPLETED · Deviations:
None · Blockers: None* — while Phase 11 shipped a defect that overwrites customer files
and Phases 05–08 produced a subsystem nothing uses.

**Velocity was never the problem here. Verification was.** Moving fast is fine; marking
unverified work complete is what produced the current state. The reviewer subagent, the
conditional definition of done, and the eval corpus exist to break that cycle.
