# CLAUDE.md — Fussion Engineering Contract

Read this before touching anything. It is the operating contract for any AI or human
contributor working in this repository.

Principles reference: <https://github.com/webpro/programming-principles>
Architecture reference: `docs/architecture/AGENT-ARCHITECTURE.md`
Scope & requirements: `docs/requirements/MVP-REQUIREMENTS-V2.md` (supersedes Phase 2 §5–§10)
Agent layer decision: `docs/architecture/ADR-001-agent-layer.md`
**What is actually realistic: `docs/FEASIBILITY.md` — read this before planning work**
How to work here: `docs/DEVELOPMENT-WORKFLOW.md` · Tooling: `docs/CLAUDE-CODE-SETUP.md`

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

**Built and working**

- Control plane: users, organizations, memberships, RBAC, JWT auth
- Projects, integrations, repositories, repository snapshots
- Knowledge base: upload, extract (PDF/MD/TXT), chunk, embed, retrieve
- Assistant configuration + widget preview
- Website integration → branch → commit → pull request pipeline
- Studio frontend: stage model, navigation, theming, SSE activity feed
- 81 backend tests, Ruff clean

**NOT built — do not write code that assumes these exist**

- **No LLM anywhere.** No model SDK, no provider, no gateway, no API key handling.
- **No agents, no harness, no orchestrator, no tool registry.**
- **No runtime plane.** No public integration key, no allowed origins, no tenant
  resolver, no visitor session, no `Conversation`/`Message`, no streaming chat,
  no rate limiting. Every route today sits behind `/organizations/{org_id}/...` auth.
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

1. **`pipeline.py` overwrites customer files.** `generate_artifacts()` accepts
   `existing_target_content` and the pipeline never passes it, so the PR replaces the
   customer's `app/layout.tsx` (or `index.html`) with a hardcoded stub. `github.py` has
   no `get_file_contents`. `StaticValidator` cannot catch it because the stub contains
   the expected markers. **This is the highest-priority defect in the repository.**

2. **`SECRET_DEV_ENCRYPTION_KEY` is hardcoded in `app/core/config.py` and committed.**
   In development it is the actual key protecting stored GitHub tokens.

3. **Generated import paths assume repo root.** Files are committed to `components/` and
   `lib/` while the component imports `@/components/...`. Any repo using a `src/` layout
   gets a build failure.

4. **Two conflicting roadmaps.** `docs/implementation/MVP-IMPLEMENTATION-ROADMAP.md`
   (19 phases) and `docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md` (12 phases) use
   colliding numbers for different work. Reconcile to one before citing a phase number.

5. **Orphaned subsystem.** `repository_snapshots`, `discovery`, `contracts`,
   `integration_adapters`, `execution_plans` (migrations 0004–0008) are referenced by
   **nothing** in the MVP integration path. Decision pending: repurpose the deterministic
   analysis for app-shell/design detection, or retire it. Do not extend it meanwhile.

6. **SSE leak.** `studio_events.py` holds an `AsyncSession` open for the life of each
   connection while polling every second. It will exhaust the pool.

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
- `app/tools/` is the only layer that touches domain services, the database, GitHub, or
  the filesystem.
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

---

## 9. Definition of done

**Always**

- [ ] Ruff clean, full backend suite passing, `pnpm build` and `pnpm test` clean
- [ ] No invariant in §4 violated
- [ ] New capability is removable by deleting a folder and one registry line
- [ ] No new `if framework ==` branch in core code
- [ ] Tenancy derived from `ExecutionContext`, never from a model-supplied value
- [ ] Alembic migration verified `upgrade → downgrade → upgrade`
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
