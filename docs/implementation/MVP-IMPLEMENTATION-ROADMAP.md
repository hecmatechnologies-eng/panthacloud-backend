# Fussion — MVP Implementation Roadmap

The locked implementation sequence for the Fussion MVP platform. Each phase builds incrementally on previous foundations and adheres strictly to the architectural decisions established in Design Phases 1–27.

---

## Phase Sequence

### Phase 01 — Repository & Development Foundation (Current Phase)
- Clean repository structure (`frontend/`, `backend/`, `docs/`, `infrastructure/`)
- Backend application foundation (FastAPI, Python venv, SQLAlchemy 2.0, Alembic)
- Frontend application foundation (Next.js, TypeScript, Tailwind CSS, pnpm)
- Database connectivity (PostgreSQL primary with dev/test SQLite fallback)
- Environment configuration (`.env.example`)
- Health check endpoints (`GET /health`)
- Basic testing foundation (Pytest + Vitest)
- CI foundation (GitHub Actions)
- Project documentation & governance

### Phase 02 — Backend Core & Identity
- Core domain entities: Users, Businesses, Memberships, Roles (RBAC)
- Authentication & session management (JWT / secure tokens)
- Tenant resolution & authorization middleware
- Initial Alembic domain migrations

### Phase 03 — Project & Integration Management
- Project boundary definition
- GitHub App integration & repository connection handling
- Secret storage & credential management
- Environment isolation (Development, Preview, Staging, Production)

### Phase 04 — Knowledge Base Foundation
- Document storage abstraction (S3-compatible)
- Text extraction & chunking pipeline
- Vector persistence (pgvector)
- Knowledge query & citation services

### Phase 05 — Repository Analysis Engine
- Codebase inspection & framework detection
- Entry-point & component discovery
- Style & design system analysis
- Analysis report generation

### Phase 06 — Orchestration & Integration Planning
- Integration Planner agent
- Deterministic state machine (Created → Analyzing → Planning → Approval → Implementing → Testing → Preview → Deploy)
- Human approval workflows & studio presentation
- Task-bound capability granting

### Phase 07 — Coding & Sandbox Execution
- Ephemeral sandbox worker integration
- Isolated code generation, patching, and file modification
- Unit/integration test execution in sandbox
- Automated bounded repair loops

### Phase 08 — Preview & Verification Layer
- Isolated preview deployment for customer repositories
- Interactive chat widget injection & validation
- Live event streaming to Fussion Studio

### Phase 09 — Runtime Engine & Production Deployment
- Deployed website assistant runtime
- Streaming conversation API (SSE/WebSocket)
- Rate limiting, token budgets, and LLM gateway routing
- Production deployment mechanisms & rollback

---

## Architectural Principles Across All Phases
1. **Control Plane vs Runtime Plane**: Never collapse administrative controls into public runtime services.
2. **Deterministic Orchestration**: LLMs operate as reasoned workers within a state machine; they do not dictate workflow state.
3. **Least Privilege**: Capabilities are granted narrowly per task and revoked upon completion.
4. **Clean Abstractions**: Rely on standard protocols (MCP, OpenTelemetry, S3 API) rather than vendor-locked libraries.
