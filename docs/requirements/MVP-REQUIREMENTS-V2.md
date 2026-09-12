# Fussion — MVP Scope & Requirements v2

**Supersedes Phase 2 §5–§10 where they conflict. Extends, does not replace, FR-001–FR-045.**

Phase 2 defined FR-001 through FR-045 before the agent architecture existed, before any
code was written, and before the product was realigned from a generic integration
platform to a website AI assistant. This document corrects the scope in light of what was
actually built, and adds the requirements that the agent layer, memory, evaluation,
resilience and production concerns introduce.

Companion to `docs/architecture/AGENT-ARCHITECTURE.md` and `CLAUDE.md`.

---

## Part A — Scope corrections to the original MVP

Phase 1 §7 listed thirteen MVP inclusions. Six are built. The corrections below reflect
what implementation revealed.

| # | Original scope item | Reality | Correction |
|---|---|---|---|
| 1 | Business account and profile | Built as `Organization` | **Rename accepted.** Docs say *Business*; code says *Organization*; a third level, *Project*, exists below it. Canonical hierarchy is `Organization → Project → resources`. Update Phase 1/2/5 terminology, not the code. |
| 2 | Document upload and knowledge-base creation | Built | Embeddings are a placeholder (see #9) |
| 3 | GitHub connection and repository selection | Built via pasted PAT | **Revised.** Phase 7 §7.7 requires GitHub App / OAuth. PAT is acceptable for MVP **only** with the encryption key moved out of source. GitHub App moves to first post-MVP item. |
| 4 | Repository and frontend framework analysis | **Not built** — user picks from a dropdown | **Restored to scope.** This is the product differentiator; without it Fussion is the chatbot builder Phase 1 §6 defines itself against. Implemented as deterministic detection first, agent for the residual. |
| 5 | Application-shell / integration-point discovery | **Not built** — user types the path | **Restored to scope.** Same reasoning. |
| 6 | Existing styling/design analysis | **Not built** | **Reduced.** MVP extracts a minimal token set (primary colour, radius, font family, spacing unit) so the widget does not look foreign. Full design-system inference is post-MVP. |
| 7 | Reusable AI chat-widget configuration and integration | Config built; widget is a non-functional button | **Revised.** Widget must be a working chat surface with Shadow DOM isolation (FR-110). |
| 8 | Secure backend connection | **Not built** | **Restored.** This is the runtime plane — public key, origin validation, session, rate limit. |
| 9 | Knowledge-grounded question answering | **Not built** — no LLM exists in the codebase | **Restored and made explicit.** Requires a real embedding provider; the deterministic hash provider is lexical matching, not semantics. |
| 10 | Streaming responses | **Not built** | **Restored.** |
| 11 | Integration branch creation | Built | — |
| 12 | Automated build/test validation | **Not built** — nothing executes | **Reduced and re-scoped.** MVP performs static validation plus a **type-check and build** inside a container sandbox. Running the customer's test suite is post-MVP. Static-only validation is not sufficient to claim "validated". |
| 13 | Pull-request creation | Built, but **overwrites customer files** | **Blocking defect.** See `CLAUDE.md` §3.1. |

### Scope items added to MVP

| Item | Why it is not optional |
|---|---|
| Agent harness + one analyst agent | Items 4, 5, 6 cannot be delivered without it |
| Model gateway with per-tenant budget | Item 9 requires a model; an uncapped tenant is an existential cost event |
| Project memory (thin) | Re-runs on the same repo must not pay full analysis cost |
| Evaluation corpus + runner | Prompts are untested code otherwise |
| Container sandbox | Item 12 requires executing customer build scripts |
| Generated-code security scan | Fussion ships JavaScript to third-party sites |
| Failure taxonomy + useful degradation | A failed run currently produces an error string and nothing else |

### Scope items removed or deferred

| Item | Decision |
|---|---|
| Phase 05–08 subsystem (snapshots, discovery, contracts, adapters, execution plans) | **Repurpose or retire.** Its adapter categories — `DATABASE`, `PAYMENT`, `CACHE`, `MESSAGE_BROKER` — are explicitly outside MVP per Phase 1 §7. The deterministic analysis machinery in `discovery.py` should be repurposed for app-shell and design-token detection; the adapter/contract/execution-plan layers retired. |
| Multi-provider model routing | Post-MVP (see the Part D YAGNI register for the trigger) |
| MCP client / server | Post-MVP — see YAGNI register |
| Durable workflow engine (Temporal) | Post-MVP — bounded job queue suffices |
| Preview environments | Post-MVP |
| Dedicated enterprise runtimes | Post-MVP |

---

## Part B — New functional requirements

### B1. Agent runtime and harness

| ID | Requirement |
|---|---|
| FR-046 | The platform shall define agents declaratively (name, version, instructions, capabilities, tool list, output schema, budget) with no infrastructure access in the agent module. |
| FR-047 | The platform shall maintain an agent registry resolving an agent name and version to its definition. |
| FR-048 | The platform shall construct an `ExecutionContext` from trusted server state carrying organization, project, repository, environment, agent, run and capability set. |
| FR-049 | An `ExecutionContext` shall never be constructed from, or modified by, model output. |
| FR-050 | The platform shall execute agents through a single harness loop: load context → assemble prompt → model call → parse structured output → authorize tool → execute → observe → update state. |
| FR-051 | The platform shall persist an `AgentRun` per execution recording state, step, attempt, budget consumption and timestamps. |
| FR-052 | An `AgentRun` shall be resumable: a retry shall not repeat successfully completed steps. |
| FR-053 | The platform shall enforce per-run budgets across tool calls, tokens, wall-clock time and estimated cost, terminating the run when any limit is exceeded. |
| FR-054 | The orchestrator, not the model, shall own workflow state transitions. |
| FR-055 | An authorized user shall be able to stop a running agent, revoking its temporary capabilities and terminating its worker. |

### B2. Memory

| ID | Requirement |
|---|---|
| FR-056 | The platform shall maintain six distinct memory tiers — working, run history, project, business knowledge, conversation, platform learning — in separate stores with independent retention and access policies. |
| FR-057 | The platform shall not provide a single unified memory store spanning these tiers. |
| FR-058 | The platform shall maintain **project memory** per repository recording detected framework/skill id, application-shell path, design tokens, package manager, build command, protected paths and prior failure reasons. |
| FR-059 | Every project-memory entry shall record the `commit_sha` from which it was derived; entries whose fingerprint does not match current HEAD shall be treated as stale and re-derived, not merged. |
| FR-060 | Project memory shall be derived data only — the system shall remain correct, though slower, if it is discarded entirely. |
| FR-061 | Project memory shall be fenced as untrusted data when placed in a model context, identically to repository content. |
| FR-062 | All memory tiers shall be tenant-scoped with an ownership path to Organization, and purged when the owning repository or project is deleted. |
| FR-063 | The platform shall not perform automatic cross-tenant learning. Knowledge generalised across tenants shall reach the system only through human-authored, reviewed Skills. |

### B3. Tools

| ID | Requirement |
|---|---|
| FR-064 | The platform shall expose a tool registry where each tool declares name, input schema, required capability and read/write classification. |
| FR-065 | All tool invocations shall pass through a single gateway performing authorization, execution and recording. |
| FR-066 | Read tools shall be auto-authorized for agents holding the corresponding read capability; write tools shall additionally require an approved plan. |
| FR-067 | Any tool able to return unbounded output shall accept `offset`/`limit` and return an explicit truncation indicator. |
| FR-068 | Tool errors shall return actionable, model-readable messages rather than stack traces. |
| FR-069 | Tool invocations shall be recorded as structured records (tool, arguments, outcome, duration), with sensitive values referenced or redacted. |
| FR-070 | Tools shall resolve resource scope from `ExecutionContext`; a resource identifier supplied in model output shall never be used directly. |

### B4. Model and cost

| ID | Requirement |
|---|---|
| FR-071 | All model access shall pass through a `ModelGateway` enforcing allowed models, maximum tokens, context limits, timeouts and retries. |
| FR-072 | The platform shall abstract model providers behind a single interface permitting substitution without changes to agents or harness. |
| FR-073 | The platform shall record input tokens, output tokens, model, provider and estimated cost for every model call, attributed to an organization. |
| FR-074 | The platform shall enforce per-organization spend budgets, triggering warning, throttling and suspension thresholds. |
| FR-075 | The platform shall report cost per integration run and cost per conversation as first-class metrics. |
| FR-076 | The platform shall use prompt caching for repeated repository context where the provider supports it. |
| FR-077 | The platform shall route inexpensive workloads (detection, classification) to a lower-cost model than planning and code generation. |

### B5. Skills

| ID | Requirement |
|---|---|
| FR-078 | Framework-specific integration knowledge shall reside in versioned skill packages, not in application code. |
| FR-079 | Adding support for a new framework shall require adding a skill package and no modification to core planning, generation or validation code. |
| FR-080 | Each skill shall declare applicability conditions and provide a deterministic detection test. |
| FR-081 | The platform shall load skills progressively — index first, then the matching skill, then only referenced templates. |
| FR-082 | The stored framework identifier shall be a skill id string, not a database enum. |
| FR-083 | Each skill shall declare paths it must never modify, in addition to platform-wide protected paths. |
| FR-083a | Skill packages shall conform to the Agent Skills specification (agentskills.io/specification): `SKILL.md` with valid `name`/`description` frontmatter, `name` matching the parent directory, and the `scripts/` `assets/` `references/` layout. |
| FR-083b | Skill packages shall be validated in CI (`skills-ref validate`); an invalid skill shall fail the build. |
| FR-083c | A `SKILL.md` body shall remain under 5,000 tokens; detailed material belongs in `references/`, loaded on demand. |

### B6. Evaluation and reproducibility

| ID | Requirement |
|---|---|
| FR-084 | The platform shall maintain a golden corpus of repository fixtures covering supported frameworks, layout variants, and at least one case that must be refused. |
| FR-085 | The platform shall provide an evaluation runner executing each agent across the corpus and asserting on structured output fields, never on exact strings. |
| FR-086 | Evaluation shall report per-case outcome plus aggregate score, token cost and wall time. |
| FR-087 | Evaluation shall run in CI on any change to a prompt, skill, agent definition or model identifier. |
| FR-088 | The platform shall maintain a labelled question set per test tenant and score runtime answers for groundedness and appropriate refusal. |
| FR-089 | Every `AgentRun` shall record agent definition version, prompt hash, model id, provider-reported model version, skill versions and tool versions. |
| FR-090 | Every `AgentRun` shall record its ordered tool-call log with sufficient fidelity to reconstruct what the agent did. |
| FR-091 | Full prompt bodies shall be retained only under a short retention window or an explicit debug flag, as they contain customer source code and business documents. |

### B7. Agent security

| ID | Requirement |
|---|---|
| FR-092 | An agent shall receive no credential of any kind; capability requests shall be resolved to credentials by the tool layer. |
| FR-093 | An agent shall not determine its own permissions; authorization shall occur outside the model before tool execution. |
| FR-094 | Capabilities shall be scoped to workflow state — analysis read-only, write granted only after approval and revoked at run end. |
| FR-095 | The platform shall reject any generated or modified file whose path is not declared in the approved plan. |
| FR-096 | The platform shall enforce platform-wide protected paths (`.env*`, `credentials/`, `.github/workflows/`, `infrastructure/`, deployment, authentication, payment and schema files) which no approved plan may override. |
| FR-097 | The platform shall scan generated code and reject dynamic evaluation, external script sources outside Fussion's origin, network calls to undeclared hosts, inline event handlers, and obfuscated payloads. |
| FR-098 | Repository content, uploaded documents, tool output, project memory and visitor messages shall be delimited and labelled as data and shall never be placed in the instruction region of a prompt. |
| FR-099 | The platform shall never merge to a customer's default branch automatically. |

### B8. Resilience and failure handling

| ID | Requirement |
|---|---|
| FR-100 | The platform shall classify every failure as retryable, terminal, needs-human or refused, and respond accordingly. |
| FR-101 | Retryable failures shall be retried with bounded attempts and backoff. |
| FR-102 | Where an integration cannot be completed, the platform shall still deliver its analysis, generated widget code and manual integration instructions rather than only an error. |
| FR-103 | The repair loop shall be bounded (default three attempts) and shall escalate to human intervention on exhaustion. |
| FR-104 | Integration runs shall be idempotent under an idempotency key; a duplicate request shall not create a second branch or pull request. |
| FR-105 | The platform shall enforce per-organization concurrency limits on integration runs. |
| FR-106 | A failed run shall leave no orphaned branch, workspace or partial commit. |

### B9. Runtime plane and widget

*Extends FR-032–FR-038 and FR-044–FR-045 with what implementation requires.*

| ID | Requirement |
|---|---|
| FR-107 | Each website integration shall have a public client key and a set of registered allowed origins. |
| FR-108 | The platform shall resolve tenant identity deterministically from the public key and validated origin before any model or retrieval call. |
| FR-109 | Retrieval shall combine tenant filtering with vector similarity; similarity alone shall never determine results. |
| FR-110 | The widget shall render inside a Shadow DOM, shall not read the host page's DOM, forms, cookies or storage, and shall degrade visibly when blocked by a Content-Security-Policy. |
| FR-111 | The platform shall document the origins the widget requires so customers can configure their CSP. |
| FR-112 | The platform shall stream responses over SSE with a defined keepalive and reconnection contract. |
| FR-113 | The platform shall rate-limit at IP, integration, session, conversation and organization levels. |
| FR-114 | A public client key shall grant chat session capability only, and shall never grant dashboard, repository, knowledge-administration, configuration or deployment access. |
| FR-115 | The runtime plane shall hold no repository write or deployment capability. |

### B10. Observability and data governance

| ID | Requirement |
|---|---|
| FR-116 | The platform shall emit OpenTelemetry-compatible traces spanning control plane, harness, tool gateway and model gateway, keyed by `AgentRun`. |
| FR-117 | The platform shall separate audit events (security, long retention, restricted access) from runtime events (UI, short retention). |
| FR-118 | Studio event streaming shall not hold a database session open for the lifetime of a client connection. |
| FR-119 | The platform shall define and enforce retention periods for visitor conversations and provide a deletion path. |
| FR-120 | A business owner shall be able to view and delete conversations belonging to their organization. |
| FR-121 | Engineering conversations and visitor conversations shall have distinct permissions, retention and visibility. |
| FR-122 | The platform shall detect and block suspicious agent behaviour (attempts to read secrets, reach internal addresses, or exfiltrate data) and raise a security event. |
| FR-123 | Workspace and sandbox teardown shall be explicit, audited and verified — workspace destroyed, environment flushed, ephemeral credentials rotated, result confirmed before any reuse. Best-effort deletion is not sufficient. |
| FR-124 | Execution resources shall never be reused across tenants without a completed and verified teardown. |
| FR-125 | Model provider access shall be isolated behind a single adapter module; no agent, harness or runtime module shall import a provider SDK or agent framework directly. |

### B11. Realism markers

The following requirements are **specified but explicitly deferred past MVP**. They remain
requirements of the design; they are not gates on the first release. See
`docs/FEASIBILITY.md` §6.

| Deferred | Interim position |
|---|---|
| FR-116 (full OpenTelemetry) | structured logs + `AgentRun` records |
| FR-122 (anomaly detection) | write allowlist + generated-code scan carry the risk |
| Scope item #12 (build validation) | static validation + explicit "build not executed" notice in the PR |
| FR-124 warm-pool reuse | no pooling at MVP — workspaces are per-run and destroyed |
| GitHub App migration | PAT acceptable once the encryption key leaves source |
| FR-084 corpus of 10–15 | start at 5, one of which is a refusal case |
| pgvector | only once real embeddings land |

---

## Part C — Revised MVP acceptance criteria

Replaces Phase 2 §10. The MVP is complete when a non-developer can:

1. Create an account, organization and project
2. Upload company documents and see them indexed with citations
3. Connect a GitHub repository
4. Start an integration and receive **automatically detected** framework, application
   shell, integration point and design tokens — without selecting a framework or typing
   a path
5. Review a plan showing exactly which files will be created and which existing files
   will be modified, with modifications visually distinguished
6. Approve the plan and receive a pull request whose diff preserves all existing file
   content
7. Merge and deploy
8. Open the widget on their live site and receive a **streamed, knowledge-grounded
   answer**, correctly attributed to their tenant, citing their uploaded documents
9. See the run's activity, cost and outcome in the Studio

And the platform must additionally demonstrate:

10. An unsupported or unanalysable repository is **refused with an explanation**, not
    integrated incorrectly
11. A failed integration still returns analysis plus manual instructions
12. Evaluation runs green across the golden corpus
13. No cross-tenant access is possible from a public client key
14. Generated code passes the security scan

---

## Part D — YAGNI register

Deliberately excluded from MVP, with the trigger that would change the decision.

| Excluded | Trigger to reconsider |
|---|---|
| MCP client/server | A customer needs to expose their own system to their assistant, or GitHub REST maintenance becomes a burden |
| Multi-provider model routing | Cost or reliability data shows a second provider is needed |
| Durable workflow engine (Temporal) | Runs routinely exceed a single worker lifetime or need human-approval timers measured in days |
| Preview environments | Customers ask to see the integrated site before merging |
| Agent-to-agent messaging | A third agent exists and serialized handoffs demonstrably bottleneck |
| Working-memory compaction | A legitimate run exceeds the context window despite bounded tool calls |
| Cross-session visitor memory | A tenant asks for it and a privacy policy covers it |
| Dedicated enterprise runtimes | An enterprise contract requires infrastructure isolation |
| Full design-system inference | Minimal token extraction proves insufficient in user testing |
| Running customer test suites | Build + type-check validation proves insufficient to catch breakage |
| PostgreSQL row-level security | Containment-path authorization proves insufficient in audit |
| More than three agents | Evals show a capability gap a prompt change cannot close |

---

## Part E — Requirement groups by build step

| Step | Requirement groups |
|---|---|
| **A. Truth & safety** | FR-095, FR-096, FR-106 · scope corrections #3, #13 |
| **B. Runtime plane** | B9 (FR-107–115), B4 (FR-071–077), FR-109, FR-119–121 |
| **C. First agent + harness + evals** | B1, B3, B5, B6 · FR-058–062 |
| **D. Coding agent + sandbox** | B7, B8, FR-063, scope corrections #4, #5, #6, #12 |
| **Throughout** | B10 (FR-116–122) |
