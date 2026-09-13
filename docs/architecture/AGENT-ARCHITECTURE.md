# Fussion — Agent Architecture

How the six agentic primitives — **Model, Harness, MCP, Skills, Sandbox, Production
Layer** — map onto Fussion, plus the cross-cutting concerns they introduce: memory, tool
design, agent security, and evaluation.

Scoped to the MVP. Companion to `CLAUDE.md`. Derived from Design Phases 1–5, 7, 8, 8.5, 9.

---

## 1. Two planes, deliberately asymmetric

Fussion contains two agentic systems with different shapes. Serving both with one
framework is over-generalization; the runtime plane needs almost none of the apparatus
the engineering plane requires.

| | **Engineering plane** | **Runtime plane** |
|---|---|---|
| Job | analyse repo → plan → code → validate → PR | question → retrieve → answer → stream |
| Volume | a few runs per tenant, ever | thousands per tenant per day |
| Duration | minutes | ~2 seconds |
| Blast radius | writes customer source code | writes nothing |
| Failure mode | corrupts a repository | answers wrongly |
| Cost per operation | dollars | fractions of a cent |

### Primitive allocation at MVP

| Primitive | Engineering plane | Runtime plane |
|---|---|---|
| **Model** | strong model, low volume | cheap/fast model, high volume |
| **Harness** | full loop, policy, budget | single-turn pipeline, no tool loop |
| **Memory** | project memory + run history | conversation memory only |
| **MCP** | defer — native tools | defer — later: customer systems |
| **Skills** | **critical** — framework knowledge | not at MVP |
| **Sandbox** | interface now, container at build validation | never — executes nothing |
| **Production Layer** | AgentRun, events, approval gate | **this *is* the production layer** |

---

## 2. MODEL

**Status: not built.** No SDK, no provider, no key handling.

**MVP:** one `ModelProvider` Protocol (`complete`, `stream`); two implementations — one
real provider, one deterministic fake for tests. All access via a `ModelGateway` facade
owning timeouts, retries, allowed-model list, token caps, and **per-tenant cost
accounting**.

**Defer (YAGNI):** multi-provider routing, cost-based fallback, dynamic context-window
governance. **Do not defer the token counter and per-business budget check**
(Phase 7 §7.26) — retrofitting metering through a gateway that recorded nothing is
painful, and an uncapped tenant is an existential cost event.

**Cost is an architectural constraint, not a finance question.** If one integration run
costs $2–4 in tokens and the target SMB price point is $10–15/month, the model is upside
down before a single conversation is served. Levers, in order of impact: deterministic
pre-analysis; prompt caching on repository context (usually the largest line item, since
the same tree and file contents are re-sent across analysis, planning and coding);
cheap model for detection and classification; progressive skill disclosure.

**Existing precedent to copy:** `GitProvider` (Protocol + factory) and
`EmbeddingProvider` (ABC) are already correctly shaped.

*Patterns: Strategy (provider), Adapter (SDK normalization), Facade (gateway).*

---

## 3. HARNESS

**Status: not built.** This is the missing core.

Everything around the model that turns a text generator into a governed worker: context
assembly, tool dispatch with authorization, loop control, budget enforcement, structured
output parsing, tracing.

**The rule that keeps it small: the harness is generic; agents are thin.**

```python
WEBSITE_ANALYST = AgentDefinition(
    name="website_analyst",
    version="1.0.0",
    instructions=...,                    # or a skill reference
    capabilities={"repository.read"},
    tools=["read_tree", "read_file", "search_code"],
    output_schema=RepositoryAnalysis,
    budget=Budget(tool_calls=40, tokens=200_000, seconds=120, cost_usd=0.50),
)
```

One loop, N agents. Target ~300–400 lines, not a subsystem. If an agent class starts
containing `database.py` or `github_client.py`, the boundary has failed.

**`ExecutionContext` is the tenancy carrier** and the most important object in the
system. Constructed by trusted infrastructure — never by the model, never from a
model-supplied identifier. Every tool call resolves scope from it.

**Runtime exception:** the visitor assistant does not run the agent loop at MVP. It is
`resolve tenant → retrieve → assemble → stream`. A tool loop there buys nothing and costs
latency on the highest-volume path.

**Agent count discipline.** Phase 8 §8.3 lists ten agent roles. MVP needs **two** —
`WebsiteAnalyst` and `CodingAgent` — possibly a third for repair. Every additional agent
adds a handoff; handoffs lose context, add latency, and multiply failure surface. Treat
the ten-role list as a capability map, not a build list.

*Patterns: Template Method (loop), Strategy (agent definitions), Chain of Responsibility
(guardrails), Command (tool invocations as objects — audit and replay for free), Memento
(AgentRun as resumable state).*

### 3.0 Execution entity model

Exactly two entities. Do **not** introduce a separate `Task` — `IntegrationRun` already
occupies that role, and three overlapping concepts is one too many.

```
IntegrationJob          the work the user requested (existing IntegrationRun)
      └── AgentRun      one agent execution within it — analysis, coding, repair …
              └── ToolCall / ModelCall / Event
```

`AgentRun` fields: id, agent_id, agent_version, organization_id, project_id, job_id,
status, current_step, attempt, execution_context, prompt_hash, model_id,
model_version_reported, skill_versions, token_usage, cost_usd, started_at, completed_at,
failure_class, failure_reason.

### 3.1 The MVP agent roster

**Two agents and one pipeline.** Everything else Phase 8 §8.3 lists is a capability that
belongs to one of these until evals prove otherwise.

| Component | Plane | Loop | Tools | Capabilities | Writes |
|---|---|---|---|---|---|
| `WebsiteAnalyst` | engineering | yes | `read_tree`, `read_file`, `search_code` | `repository.read` | nothing |
| `CodingAgent` | engineering | yes | `read_file`, `write_file`, `apply_patch` | `repository.read`, `workspace.write` | workspace only |
| Runtime assistant | runtime | **no** — single-turn pipeline | none | — | nothing |

**Deliberately not separate agents:**

- **IntegrationPlanner** — deterministic at MVP. Given an analysis and a matched skill,
  the plan is a pure function. Escalate to the model only when no skill template matches.
- **RepairAgent** — the `CodingAgent` in repair mode: same tools, same capabilities,
  different instructions plus the validation result. A second agent here would buy a
  handoff and lose context.
- **Design/Knowledge analysts** — folded into `WebsiteAnalyst` and the existing knowledge
  pipeline respectively.

### 3.2 Agent contracts

**`WebsiteAnalyst`** — read-only understanding of a customer repository.

```
in   ExecutionContext(org, project, repository, commit_sha)
     + deterministic pre-analysis (manifest, file tree, dependency list)
     + skill index (names + one-line descriptions)
out  WebsiteProfile {
       framework_skill_id: str | None
       router: str | None                  # e.g. "app" | "pages" — changes the target
       language: str
       package_manager: str
       build_command: str | None
       entry_points: [str]
       integration_candidates: [            # RANKED, not a single answer
         { path: str, confidence: float, reason: str }
       ]
       styling_system: str | None
       design_tokens: { primary_color, radius, font_family, spacing_unit }
       protected_paths: [str]
       unsupported_reason: str | None      # REQUIRED when the repo cannot be handled
     }
budget  40 tool calls · 200k tokens · 120s · $0.50
```

Two contract decisions worth holding:

**`integration_candidates` is a ranked list, never a single path.** Below a confidence
threshold the Studio presents the alternatives and a human chooses. A single answer forces
the agent to guess.

**`unsupported_reason` is not an error path** — it is a first-class successful outcome. An
analyst that guesses on an unrecognisable repository is worse than one that declines.

**`CodingAgent`** — implements an approved plan inside the workspace.

```
in   ExecutionContext + approved IntegrationPlan + matched skill package
     + real file contents read from the workspace
     + (repair mode) ValidationResult
out  ChangeSet {
       files: [{ path, action: create|modify, diff, rationale }]
       notes: [str]
       blocked: [{ path, reason }]
     }
budget  60 tool calls · 300k tokens · 300s · $1.50
```

The agent writes to the **workspace only**. Committing and opening the pull request is
performed by the platform from the resulting `ChangeSet`, never by the agent.

**Runtime assistant** — not an agent loop.

```
resolve tenant → retrieve chunks → assemble fenced context → stream → persist message
```

No tools, no loop, no repository access at MVP. Tenant-scoped retrieval is performed by
the pipeline before the model is called, never requested by the model.

---

## 4. MEMORY

Phase 8 §8.17 says *"separate task state, project memory, and business knowledge instead
of creating one unrestricted memory store."* This is what that means concretely.

### The six tiers

| Tier | Scope | Lifetime | Store | MVP |
|---|---|---|---|---|
| **Working memory** | one agent run | the run | in-process message list | yes |
| **Run history** (episodic) | one run, replayable | retained | `AgentRun` + `ToolCall` + `Event` | yes |
| **Project memory** | one repository | across runs, invalidated by commit | `ProjectMemory` table | yes, thin |
| **Business knowledge** | one tenant | durable | KnowledgeBase + pgvector | exists |
| **Conversation memory** | one visitor session | session + TTL | `Conversation` / `Message` | yes |
| **Platform learning** | cross-tenant | curated | **Skills, human-authored** | via skills only |

### Working memory

The message and tool-result history inside one run. Bounded by the run budget.

At MVP, **bound the run so compaction is never needed** — focused tasks, ≤40 tool calls,
paginated tool output. Summarization/compaction of older turns is a real technique but it
is YAGNI until a run legitimately exceeds context, and premature compaction silently
drops the detail that made the run correct.

### Project memory — the one with real product value

Durable knowledge about *this customer's repository*: detected framework and skill id,
app-shell path, styling system and design tokens, package manager, build command,
protected paths the owner flagged, what failed last time and why.

Why it matters: the second integration run on the same repo — a re-integration after the
site changed, a widget restyle, a retry — should be dramatically faster and cheaper than
the first. That is the difference between a $3 run and a $0.30 run.

Rules:

1. **Derived data, never a system of record.** Everything in it must be reconstructible
   by re-running analysis. If losing it breaks correctness rather than just performance,
   it has become a database and the boundary is wrong.
2. **Fingerprinted.** Every entry carries the `commit_sha` it was derived from. A
   different HEAD means stale — ignore and re-derive, do not merge.
3. **Untrusted on read-back.** Project memory is written from repository content, which
   is untrusted. An agent writing memory in run 1 and reading it in run 2 is a
   cross-run prompt-injection path. Fence it in the context exactly like repo content:
   labelled data, never instruction.
4. **Tenant-scoped with the same ownership path** as every other resource, and purged
   when the repository is disconnected or the project deleted.
5. **Structured, not prose.** A typed record the platform can validate, not a free-text
   scratchpad the model appends to.

### Conversation memory

Multi-turn within a visitor session. Across sessions is a privacy decision, not a
feature decision — default off at MVP. Retention policy and a deletion path are
requirements, not niceties (visitors type whatever they type, and Uganda's Data
Protection and Privacy Act 2019 applies).

Streaming tokens do not become individual permanent records (Phase 9 §9.27).

### Platform learning — the important restriction

There is a tempting design where the platform automatically learns across tenants:
"integrations that looked like X succeeded with approach Y." **Do not build this as an
automatic memory store.** It is a tenant-isolation hazard by construction — one
customer's repository shape influencing another customer's integration is exactly the
cross-tenant leakage the whole architecture exists to prevent.

The safe and equally compounding form: **failures observed in evals and production get
read by a human and written into Skills.** Curated, reviewed, tenant-free, versioned,
diffable. Skills are the institutional memory. That keeps the isolation invariant intact
while still getting better every week.

### The invariant

**Never merge tiers into one store.** A single `memories` table holding run state,
repository facts, business documents and visitor chat is the failure mode Phase 8 §8.17
warns about — it destroys retention policy, access control, and tenancy in one move.

---

## 5. MCP

**MVP decision: do not use it yet.** Define the `Tool` Protocol so an `MCPToolProvider`
drops in later as one more implementation.

MCP's value is third-party interoperability and dynamic capability discovery. At MVP
Fussion owns every capability, so an MCP client adds a process boundary, a transport, a
discovery handshake, and new failure modes for no benefit.

**MCP is not the internal transport between Fussion's own components.** A tool is the
capability; MCP is a protocol for exposing capabilities across an ownership boundary.

**Where it will earn its place**

1. GitHub's official MCP server replacing hand-rolled REST — a convenience swap, not
   urgent; `github.py` is ~200 lines and fully controlled.
2. **Customer-exposed systems** — a business connecting its own CRM, inventory, or
   booking system so its runtime assistant can query it. The real long-term play, and the
   reason the Tool abstraction must be provider-agnostic from day one.

---

## 6. SKILLS — the highest-leverage decision

### The problem

`planner.py` and `artifacts.py` hard-code Next.js and generic HTML in `if/elif` branches.
Adding Vue means editing the `WebsiteFramework` enum, an Alembic migration (it is a DB
enum), `planner.py`, `artifacts.py`, `validation.py`, the frontend type union, and the
tests. **Seven places.** "Works on any website" is the product promise; this structure
cannot deliver it.

### The structure — conform to the Agent Skills open spec

Fussion skills follow the **Agent Skills specification** (<https://agentskills.io/specification>),
not a private format. Same layout, same frontmatter, same progressive-disclosure model,
and `agentskills validate` runs in CI for free.

```
skills/integrations/nextjs-app-router/
├── SKILL.md          # required — frontmatter + instructions, < 500 lines
├── scripts/
│   └── detect.py     # deterministic match test
├── assets/
│   ├── FussionAssistant.tsx.j2
│   └── config.ts.j2
└── references/
    └── EDGE-CASES.md # src/ layout, custom provider stacks, monorepos
```

```yaml
---
name: nextjs-app-router            # 1–64 chars, lowercase/digits/hyphens,
                                   # MUST match the parent directory name
description: >                     # ≤ 1024 chars — what it does AND when to use it.
  Integrates the Fussion assistant widget into a Next.js App Router project by
  patching the root layout. Use when package.json depends on next >= 13 and an
  app/ directory with layout.tsx is present.
compatibility: Requires a Node project with a resolvable package manager lockfile
metadata:
  fussion.framework: nextjs
  fussion.router: app
  fussion.schema_version: "1"
---
```

**Why conform rather than invent:** models are already trained on this format, so skill
bodies are interpreted as intended; validation tooling exists; and if Fussion ever accepts
community-contributed framework skills or exposes skills to customers, it is already a
standard artefact rather than a proprietary one.

### Token budget — the concrete numbers

The spec's progressive-disclosure tiers give real figures to design against:

| Tier | Loaded when | Budget |
|---|---|---|
| `name` + `description` | at startup, for **every** skill | ~100 tokens each |
| `SKILL.md` body | when the skill is activated | **< 5,000 tokens** (keep under 500 lines) |
| `scripts/` `assets/` `references/` | only when referenced | on demand |

So twenty framework skills cost ~2,000 tokens of always-on index, and only the matched one
loads in full. That is the context economy claim, quantified.

Keep file references **one level deep** from `SKILL.md` — avoid nested reference chains.

Adding Nuxt, SvelteKit, Astro, WordPress = **one folder each**. No core edits, no
migrations. The `framework` column becomes a skill id string instead of a DB enum,
removing the migration cost entirely.

### Why it beats code generation

`SKILL.md` is model-readable, so the Coding Agent receives integration knowledge as
*context* rather than the platform emitting fixed output. That is what lets it handle the
repo that is *almost* standard Next.js but keeps its layout at `src/app/layout.tsx`
behind a custom provider stack. The template is a starting point, not the answer.

Hard-coded generation cannot adapt — which is exactly why today's pipeline emits imports
that break `@/` alias resolution on any `src/`-layout repository.

### Context economy

Progressive disclosure falls out for free: read the skill index (names + one-line
descriptions, cheap) → load only the matching `SKILL.md` → load only the templates it
references. A direct answer to Phase 4 §14, *"do not send the entire repository on every
model call."*

### Skills as institutional memory

Skills are versioned, diffable, reviewable content. When an eval run or a production
failure reveals that a framework needs different handling, the fix is a skill edit —
reviewed by a human, applied to every tenant, with no cross-tenant data movement. This is
how Fussion compounds knowledge safely.

### The payoff

Framework coverage stops being an engineering cost and becomes a content cost. That is
the difference between supporting 2 frameworks and supporting 20.

*Patterns: Strategy per framework, Registry, Template Method, Open/Closed.*

---

## 7. SANDBOX

**`SandboxManager` is not a sandbox.** It is a directory with (good) path-containment
checks. The name is dangerous — someone will assume isolation exists.

**MVP**

- Rename `SandboxManager` → `WorkspaceManager`.
- Define `SandboxProvider` Protocol: `run(command, timeout, network_policy) -> Result`.
- Ship `LocalWorkspaceProvider` whose `run()` **raises** — a Null Object that fails
  loudly rather than silently executing on the control plane.

**When the real thing becomes mandatory:** the moment integration validation is real.
Verifying a widget integration requires `npm install && npm run build` on customer code,
and npm lifecycle scripts execute arbitrary code (Phase 7 §7.32). That day you need a
container with CPU/memory caps, no network by default, and an ephemeral filesystem.
Non-negotiable, not a hardening nice-to-have.

**Immediate value:** the workspace is where *reading the customer's real file* happens.
Shallow-clone → read the actual `app/layout.tsx` → patch that → push. This fixes the
live overwrite defect and gives the analyst agent a real filesystem, in one change.

**Teardown is security-critical, not housekeeping.** Incomplete cleanup between tenants is
the most common security regression in agent platforms. Destruction must be explicit and
audited: workspace removed, environment flushed, ephemeral credentials rotated, and the
result *verified* before any reuse. This applies to the workspace today and to warm
container pools later. `pipeline.py` cleaning up in a `finally` is the right instinct; it
needs to become a verified, logged operation rather than a best-effort `rmtree`.

**MVP reality check.** Build validation is the heaviest infrastructure dependency in the
plan and sits on the critical path only because Phase 1 §7 listed it. See
`docs/FEASIBILITY.md` §4 — the recommendation is to cut it from MVP, ship static
validation plus an honest "Fussion did not execute your build" note in the PR, and keep
the Protocol so the container is additive later.

---

## 8. PRODUCTION LAYER

Everything that makes this a product rather than a script. For Fussion this is the entire
visitor data plane — **0% built**, and the MVP promise depends on it.

```
Widget → public key + Origin → TenantResolver → VisitorSession
       → RateLimit → BudgetCheck → Retrieval → ModelGateway → SSE stream
       → Conversation/Message + UsageRecord + trace span
```

**Hardest invariant:** tenant identity is resolved by deterministic infrastructure before
the model sees a single token. No prompt can cross tenants because tenancy was decided
before the prompt existed. Make it structurally impossible, not a convention — the
`ExecutionContext` should be the only way any tool or retrieval call can name a business.

**Prompt injection** (Phase 7 §7.15–7.19) is a context-assembly problem, not a
model-behaviour problem. Retrieved documents, repository files and project memory are
data: delimited, labelled, never concatenated into the instruction region. Do not ask the
model to be careful.

**Widget isolation on the customer's site.** The widget is third-party JavaScript running
on someone else's domain:

- **Shadow DOM**, so their CSS cannot break the widget and the widget cannot break their
  site. Without it, Tailwind-reset support tickets arrive on day one.
- **CSP compatibility** — many real sites have a Content-Security-Policy that will block
  an inline script or an unlisted `connect-src`. Document required origins; expect to be
  blocked and fail visibly rather than silently.
- **Never read the host page's DOM, forms, cookies or storage.** An invariant, so nobody
  adds a "helpful" page-context feature later.
- **SRI** if distributed via CDN.

**Observability.** OTel spans keyed by `AgentRun`, plus the structured events the Studio
already streams. Two fixes needed: separate audit events (security, long retention) from
runtime events (UI, short retention) per Phase 7 §7.34; and stop `studio_events.py`
holding a DB session open while polling every second.

---

## 9. Module layout

```
backend/app/
├── agents/              # thin declarations only — zero infrastructure
│   ├── base.py          # AgentDefinition
│   ├── registry.py
│   └── website_analyst.py
├── harness/
│   ├── context.py       # ExecutionContext — the tenancy carrier
│   ├── loop.py          # the one agent loop
│   ├── authorization.py # capability checks
│   ├── budget.py        # tokens, tool calls, wall clock, cost
│   ├── tracing.py
│   └── run.py           # AgentRun persistence
├── memory/
│   ├── project.py       # ProjectMemory — derived, fingerprinted, tenant-scoped
│   └── conversation.py
├── tools/
│   ├── base.py          # Tool Protocol (name, schema, capability, read|write)
│   ├── registry.py
│   ├── gateway.py       # single choke point: authorize → execute → record
│   ├── repository.py
│   └── knowledge.py
├── llm/                 # NOT models/ — app/models/ is SQLAlchemy
│   ├── base.py          # ModelProvider Protocol
│   ├── gateway.py
│   └── providers/
├── skills/
│   ├── loader.py
│   └── integrations/<framework>/
├── execution/
│   ├── base.py          # SandboxProvider Protocol
│   ├── local.py         # refuses to execute
│   └── container.py     # later
├── evals/
│   ├── corpus/          # golden repositories
│   ├── cases.py
│   └── runner.py
└── runtime/             # visitor data plane
    ├── resolver.py
    ├── session.py
    └── chat.py
```

---

## 10. Tool design standards

Most agent failures in practice are **tool** failures, not reasoning failures. The tools
are the agent's entire interface to the world and are usually written as an afterthought.

1. **Few tools, unambiguous names.** `read_file`, `read_tree`, `search_code` — not
   fifteen overlapping variants. Overlap produces wrong-tool selection, which presents as
   a model problem and is not one.
2. **The docstring is the prompt.** Write tool descriptions for the model, not for a
   developer reading the module.
3. **Outputs sized for context.** `read_file` on a 4,000-line file destroys the window.
   Every tool that can return unbounded data takes `offset`/`limit` and returns an
   explicit truncation signal the model can act on. `search_code` caps results and states
   how many were omitted.
4. **Errors that teach.** `"File not found: components/App.tsx. Did you mean
   src/components/App.tsx?"` recovers in one turn. A stack trace burns three.
5. **Read/write typed at the interface.** Read tools are auto-authorized; write tools
   require a granted capability and an approved plan. This is the authorization model,
   not a style preference.
6. **Idempotent where possible.** Re-running a tool with the same arguments should be
   safe. `artifacts.py` already gets this right at the file level with `BEGIN`/`END`
   markers — apply the same thinking at the tool level.
7. **No tool returns raw internal identifiers** the model could later echo back as a
   resource selector. Scope always resolves from `ExecutionContext`.

This is webpro's **Robustness Principle** applied to a probabilistic consumer: liberal in
what the tool accepts, and maximally recoverable in what it returns.

---

## 11. Agent security

Beyond the credential and tenancy invariants in `CLAUDE.md` §4, agents that *write code*
introduce a category the design docs do not currently cover.

### Fussion occupies a supply-chain position

Fussion writes JavaScript that runs on a customer's website, in their visitors' browsers,
under their domain. That is the same trust category as an npm package.

**Attack path:** a malicious repository README, a crafted file comment, or a poisoned
dependency name persuades the coding agent to emit a widget that also exfiltrates form
data or loads a remote script. Prompt injection here does not leak Fussion's data — it
backdoors the *customer's site*, in a pull request carrying Fussion's name.

### Controls

1. **Write allowlist.** The agent may only create or modify paths declared in the
   approved plan. `StaticValidator` already rejects files outside
   `plan.files_to_create + files_to_modify` — keep that strict and never relax it.
2. **Semantic scan of generated output**, not only markers and secrets. Reject: `eval`,
   `new Function`, `<script src>` to any origin except Fussion's, `fetch`/`XHR` to an
   undeclared host, inline event handlers, obfuscated or base64-encoded payloads.
   Roughly 40 lines on an existing hook, and it closes the whole category.
3. **Protected paths are absolute.** `.env*`, `credentials/`, `.github/workflows/`,
   `infrastructure/`, deployment config, auth, payments, database schemas
   (Phase 7 §7.13, Phase 4 §16). Not negotiable by an approved plan.
4. **Untrusted content is fenced** — repository files, documents, tool output, project
   memory, visitor messages. Delimited and labelled as data, never in the instruction
   region.
5. **Capability narrowing by state** (Phase 4 §10): ANALYZING is read-only; write
   capability is granted only after approval and revoked at run end.
6. **Kill switch** (Phase 7 §7.36): an authorized user can stop a run, revoke its
   temporary capabilities, and terminate its worker.

### Human approval must be real, not theatre

A human approves a diff. If the diff is large, unexplained, or mixes new files with edits
to existing code, they will rubber-stamp it — and the safety story collapses. Keep
changes minimal, annotate each file with why it is there, and visually separate
**new files** from **modifications to existing code**. Modifications are where the risk
lives.

---

## 12. Evaluation

The largest omission in the original design docs. The moment a model is in the loop,
**prompts become code without tests.** Change a system prompt, edit a skill, or accept a
provider's silent model update, and you have shipped an untested change to the most
important logic in the product. Unit tests cannot catch it; the output is not
deterministic.

Required from agent #1, not from a later hardening phase.

### Golden corpus

`backend/tests/fixtures/repositories/` already has ten demo repos built for the Phase
05–08 contract work. The pattern is right; build the integration equivalent:

- Next.js app router · Next.js pages router · `src/` layout variant
- Vite + React · plain static HTML · Astro or SvelteKit
- One with an unconventional custom app shell
- **At least one that should be refused** — unanalysable, or no safe integration point

**Refusal cases matter as much as success cases.** An agent that confidently picks the
wrong file on an unrecognisable repo is worse than one that says it cannot determine the
app shell. Half the corpus should test judgment, not capability.

### Harness

Run each agent across the corpus, assert on **structured output fields** — framework
detected, entry point located, integration point chosen, risk level, refusal raised —
never on exact strings. Temperature 0 is not reproducible across model versions.

Report per-case pass/fail plus aggregate score, token cost, and wall time. Run it in CI
on any change to a prompt, a skill, an agent definition, or a model id.

### Runtime quality

A small human-labelled Q&A set per test tenant, graded by a judge model against the
source documents, scoring groundedness and refusal-when-unsupported. It is the only way
retrieval regressions become visible before customers find them.

### Reproducibility

Every `AgentRun` records: agent definition version, prompt hash, model id **and** the
version string the provider returned, skill versions used, tool versions, and the ordered
tool-call log.

Providers silently update models behind a stable name, so "we used model X" is not an
answer when a PR is found to have broken a customer's site months later. For a product
that modifies customer property this is a liability position, not just a debugging
convenience. It costs a few columns now and cannot be reconstructed later.

Full prompt bodies contain customer source code and business documents — store structured
tool calls always, prompt bodies behind a short retention window or a debug flag.

---

## 13. Resilience and failure handling

`pipeline.py` today catches `Exception`, writes `error_message`, and raises. That is one
failure mode for a system with about eight.

**Classify every failure:**

| Class | Examples | Response |
|---|---|---|
| Retryable | rate limit, timeout, transient 5xx | bounded retry with backoff |
| Terminal | repo not found, permission denied | fail, explain, stop |
| Needs-human | repair loop exhausted, ambiguous shell | escalate, preserve state |
| Refused | unsupported framework, protected path required | decline with reasoning |

**Degrade to something useful.** If the integration cannot be completed, still deliver
the analysis — detected framework, app shell, the widget code, and the one line to add
manually. The customer gets most of the value and you keep the account. A red error
screen gets you a churn.

**Partial progress must survive.** If planning fails, a retry must not re-run analysis.
This is what makes `AgentRun` a resumable memento rather than a log row — and it is also
a direct cost saving.

**Idempotency.** Clicking "Start integration" twice today produces two branches and two
pull requests. Runs need an idempotency key and deduplication.

**Concurrency limits on the engineering plane**, not only the runtime. One tenant must
not be able to launch fifty simultaneous runs.

**Rollback path.** Branch + PR means an unmerged change is closed and gone. Document the
revert path for a merged one; it is cheap because it is git, but it must be written down.

---

## 14. Agentic patterns

**Adopt**

- **Orchestrator–workers**, not an autonomous swarm. The orchestrator owns workflow
  state; the model reasons inside a state it cannot change (Phase 8 §8.2, §8.22).
- **Evaluator–optimizer** repair loop: implement → validate → diagnose → repair, bounded
  at 3, then escalate. Bound it in the harness budget so no agent can opt out.
- **Routing:** cheap model for classification and detection, strong model for planning
  and code generation.
- **Structured output as the determinism boundary.** Unparseable output is a failed step,
  not a best-effort string. This is what makes a probabilistic component safe to depend
  on.
- **Human approval as a first-class workflow state**, not a UI flag.
- **Context engineering:** progressive disclosure, layered context, sub-agent isolation
  for large reads.

**Avoid**

- **Using the model where determinism works.** See `CLAUDE.md` §7.
- **One giant autonomous agent with broad access.** Explicitly rejected by Phase 4 §1.
- **An agent that owns a domain.** Agents reason; the platform owns state, identity,
  permissions, tools, validation, persistence, audit, and safety.
- **Automatic cross-tenant learning.** See §4.

---

## 15. Build sequence

The harness grows only as much as the agents in it demand.

**A. Truth & safety** — fix the layout overwrite (clone + read the real file); one
roadmap; rename `SandboxManager` → `WorkspaceManager`; remove the hardcoded dev
encryption key; decide the fate of Phases 05–08.

**B. Runtime plane** — the Production Layer box. Forces `ModelGateway` v0 into existence
under real traffic. Real embeddings + pgvector. Conversation memory. The MVP promise
becomes demonstrable, at near-zero risk since nothing writes to customer repos.

**C. First agent + thin harness + evals** — `WebsiteAnalyst`, read-only tools,
deterministic pre-analysis feeding it, Skills structure with two frameworks, golden
corpus and eval runner from day one. Read-only means the policy layer has little to
defend against — the right conditions for learning what it actually needs to do.

**D. Coding agent + harness hardening + container sandbox** — write capability, generated
code scanning, build validation, bounded repair, project memory. The harness earns its
complexity here, because two real agents are now telling you what it needs.

---

## 16. Open decisions

| Decision | Options | Status |
|---|---|---|
| Phases 05–08 subsystem | repurpose for app-shell/design detection · retire | open |
| Phase numbering | 19-phase roadmap · 12-phase tracker | must reconcile |
| Sequence | runtime-first · harness-first | open |
| Embeddings | swap now · after runtime plane | open |
| Integration runs | job queue now · inline until sandbox lands | open |
| Cross-session conversation memory | off · opt-in per tenant | open (default off) |
