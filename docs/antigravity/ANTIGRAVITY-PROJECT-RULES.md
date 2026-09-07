# Fussion — Antigravity Global Engineering Rules

## 1. Architectural Authority Hierarchy

When resolving technical decisions, consult authoritative documents in this strict order:

1. **Approved Design Phases 1–27**
2. **MVP Implementation Roadmap** (`docs/implementation/MVP-IMPLEMENTATION-ROADMAP.md`)
3. **Antigravity Project Rules** (`docs/antigravity/ANTIGRAVITY-PROJECT-RULES.md`)
4. **Current Phase Tracker** (`docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md`)
5. **Current Phase Implementation Prompt**
6. **Current repository implementation**

If these sources conflict, do not silently choose an interpretation. Stop at the smallest reasonable boundary and report the conflict.

---

## 2. Architectural Boundaries

### Control Plane vs Runtime / Data Plane
- **Control Plane**: Manages identity, tenants, projects, policies, approvals, billing, usage, agent registry, and protected secrets. It is the authoritative security boundary.
- **Runtime / Data Plane**: Serves deployed customer assistants, executes authorized runtime conversations, and performs knowledge retrieval.
- **Rule**: Never collapse these planes. Runtime agents must never inherit GitHub write, repository modification, or deployment capabilities.

### Orchestrator vs LLM
- The deterministic orchestrator owns workflow state and coordinates long-running engineering jobs.
- The LLM does NOT decide its own permissions or own authoritative workflow state. The LLM operates strictly inside defined states and permissions.

### Harness vs Sandbox
- The agent harness surrounds reasoning with instructions, context, memory, tool permissions, guardrails, and tracing.
- The sandbox contains risky code execution (builds, tests, dependency installs) in isolated ephemeral workers.
- Build and test operations must NEVER execute directly on the Fussion control-plane server.

---

## 3. Engineering & Implementation Principles

### 1. Do not reinvent mature infrastructure
Use established frameworks and libraries. Do NOT build custom:
- HTTP frameworks
- Authentication systems
- ORM
- Database drivers
- Task queues
- Logging frameworks
- Container orchestration
- Validation frameworks

### 2. YAGNI (You Aren't Gonna Need It)
Do not implement future functionality merely because the architecture supports it.
Unless explicitly pulled forward in the current phase prompt, do NOT implement:
- MCP
- Sandbox
- Autonomous tool execution
- Multi-agent orchestration
- Generated MCP servers
- Customer-managed runtime
- Advanced memory
- Billing
- Enterprise deployment

### 3. Avoid premature abstractions
Do NOT introduce:
- Repositories everywhere
- Factories everywhere
- Service classes without a real responsibility
- Unnecessary interfaces
- Microservices
- Event buses
- Complex dependency-injection frameworks

### 4. Inspect before modifying
Before changing existing code:
- Understand it
- Determine why it exists
- Identify its dependencies
- Preserve working behavior unless there is a reason to change it

---

## 4. Security & Environment Principles

- **Never commit secrets**: Use `.env.example` templates. Exclude `.env` and credential files in `.gitignore`.
- **Tenant Isolation**: Business is the primary tenant. Business A must never access Business B's data or credentials.
- **Database Fallback Policy**:
  - PostgreSQL is the primary system of record.
  - SQLite fallback is strictly limited to local development and testing.
  - Production (`APP_ENV=production`) MUST fail loudly if PostgreSQL is unavailable; silent fallback in production is strictly prohibited.
- **CORS Policy**: CORS must be configuration-driven. Never use `allow_origins=["*"]` in production.
- **Health Check Privacy**: Public health endpoints (`GET /health`) must return only clean operational status without leaking internal database engines, versions, or latency metrics.

---

## 5. Phase Discipline

- Each implementation phase has a strict Definition of Done.
- Do NOT begin subsequent phases automatically upon completion of the current phase.
- Record completed work, decisions, deviations, and blockers in `docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md`.
- Wait for the user's explicit prompt before proceeding to the next phase.
