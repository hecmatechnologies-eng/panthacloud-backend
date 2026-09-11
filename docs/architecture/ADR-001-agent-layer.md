# ADR-001 — Agent layer: adopt Pydantic AI, build the harness

**Status:** Accepted · **Date:** 2026-09-11 · **Supersedes:** none

---

## Context

Fussion needs an agent layer. The question is whether to adopt an open-source agent
framework, build everything, or split.

Design Phase 8.5 §8.5.5 and §8.5.26 require provider abstraction and freedom from
vendor lock-in. Phase 8 §8.22 requires that the orchestrator — not the LLM and not a
framework — owns authoritative workflow state. Phases 5 and 7 require that tenant
identity, capability authorization and budget enforcement sit outside the model.

The existing codebase is FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic.

The decisive finding from the 2026 landscape survey: **no open-source agent framework
provides multi-tenant isolation.** LangGraph, CrewAI and AutoGen all leave it to the
platform. Tenant isolation, per-tenant budgets, capability scoping and audit are
precisely Fussion's risk surface, and precisely what no framework ships.

---

## Decision

**Split the layer in two.**

**1. Adopt Pydantic AI as the agent layer** — the commodity ~80%:

- agent loop and tool dispatch
- tool schemas generated from type hints and docstrings
- structured output (`output_type=BaseModel`) with validation and `ModelRetry`
- model-agnostic providers
- streaming (`run_stream`)
- OpenTelemetry tracing and token accounting
- durable-execution adapters (Temporal, DBOS, Prefect) available but unused at MVP

**2. Build Fussion's harness** — the part no framework provides:

- `ExecutionContext` construction and propagation (tenancy carrier)
- tool gateway with capability authorization scoped to workflow state
- per-tenant cost budgets and quota enforcement
- context fencing for untrusted content
- `AgentRun` persistence, resumability, and reproducibility metadata
- skills loader and progressive disclosure
- human approval gates
- generated-code security scanning

**3. Wrap it.** Agents and harness depend on **Fussion's own** `ModelProvider` and
`AgentRunner` Protocols. Pydantic AI is an implementation behind them, imported in one
adapter module and nowhere else. Swapping frameworks later is one file, not a rewrite.

**4. The runtime plane uses no framework.** `retrieve → assemble → stream` is a direct
provider call. No agent library on the highest-volume, lowest-latency path.

---

## Rationale

- Same lineage as the existing stack. Pydantic v2 is already the schema layer; agents
  become typed Pydantic models rather than a new mental model.
- `deps_type` dependency injection is the natural carrier for `ExecutionContext`, and
  `override` makes it testable with a mock.
- `output_type=BaseModel` *is* the structured-output determinism boundary the
  architecture requires — unparseable output becomes a failed step, for free.
- It stops where it should: "provides the agent layer but doesn't include orchestration,
  scheduling, or state management." That boundary is exactly where Fussion's own
  responsibility begins.
- Least code to write and maintain, which matters given team size.

---

## Alternatives considered

| Option | Rejected because |
|---|---|
| **LangGraph** | Strong durable execution and checkpointing, production-proven — but YAGNI for two agents in a linear flow, carries LangChain abstraction weight that teams report working against them at scale, and its state lives in framework checkpoints rather than Fussion's Postgres domain model, fragmenting `AgentRun` ↔ `IntegrationJob`. **Revisit if runs must survive restarts and span days.** |
| **CrewAI** | "Architecture feels rigid and opaque"; "debugging painful because engineers don't know what prompts are sent to the LLM." Incompatible with FR-089/FR-090 reproducibility. |
| **AutoGen** | Maintenance mode since October 2025. |
| **OpenAI Agents SDK / Claude Agent SDK** | Provider-coupled, violating Phase 8.5 §8.5.26. The Claude Agent SDK is additionally forbidden in product code per `CLAUDE.md` terminology rules. |
| **Bedrock AgentCore** | Provides real multi-tenant isolation, but AWS lock-in and per-run cost incompatible with target margins. |
| **Build everything** | The loop, tool schema generation and structured-output retry are commodity. Writing them buys nothing and costs weeks. |

---

## Consequences

**Positive** — less code to own; structured output and tracing arrive free; model
swapping is a config change; the harness stays small and focused on what is genuinely
Fussion's.

**Negative** — a dependency that can change under us; the adapter boundary must be
enforced in review or the library will leak into agents; Logfire tracing is a second
observability surface to reconcile with Studio events.

**Enforced by** — `fussion-reviewer` checks that `pydantic_ai` is imported only in
`app/llm/adapters/` and nowhere in `app/agents/` or `app/harness/`.

---

## Follow-on decisions recorded here

**`Task` is not a separate entity.** The thread that prompted this ADR proposed
`Task` alongside `AgentRun`, but `IntegrationRun` already exists. Three overlapping
concepts is one too many. Canonical model:

```
IntegrationJob   the work the user requested
      └── AgentRun   one agent execution within it (analysis, coding, repair …)
```

**`WebsiteAnalyst` output adopts two improvements** from that thread — a `router` field
(app vs pages materially changes the integration point) and `integration_candidates` as a
**ranked list with confidence** rather than a single path, so the Studio can offer
alternatives and a human can choose when confidence is low.

**`knowledge_analyst` and `integration_planner` are not agents at MVP.** Knowledge
ingestion is an existing deterministic pipeline; the integration plan is a pure function
of an analysis plus a matched skill. Escalate to a model only when no skill matches.
