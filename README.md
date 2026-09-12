# Fussion — AI Integration Engineer Platform

> Transform your website and company knowledge into an autonomous, branded AI assistant.

Fussion is an **AI Integration Engineer Platform**. Rather than providing a simplistic embed script, Fussion acts as an automated software engineer that connects to your repository, analyzes your frontend architecture and styling, produces an integration plan for human approval, and implements, tests, and verifies a knowledge-grounded assistant in an isolated sandbox.

---

## Current status

**Pre-MVP, under active development. Not deployable, and not yet demonstrable end to end.**

The control plane works: accounts, organizations, projects, RBAC, the knowledge base, assistant
configuration and the Studio. There is **no LLM in the codebase**, no live GitHub connection, and
no visitor runtime yet, so the product promise — a knowledge-grounded assistant answering on a
customer's site — is not yet deliverable.

**[`CLAUDE.md` §2](CLAUDE.md) is the single source of truth for what exists.** It is read at the
start of every working session, so it stays honest; this section deliberately does not repeat its
detail, because duplicating it is how this README came to claim "Phase 01 Complete" through
eleven phases.

- **Plan**: [docs/FEASIBILITY.md](docs/FEASIBILITY.md) §3 — steps A–D, sliced per step in
  [docs/implementation/](docs/implementation/). Work is identified as a step and slice
  ("step B, slice B1"), never a phase number.
- **Progress**: [docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md](docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md)
  — step status at the top; its numbered phase table is historical record only.
- **Scope**: [docs/requirements/MVP-REQUIREMENTS-V2.md](docs/requirements/MVP-REQUIREMENTS-V2.md)

---

## System Architecture & Governance

Fussion follows the approved system architecture designed in **Phases 1–27**:

- [CLAUDE.md](CLAUDE.md) — the engineering contract: invariants, boundaries, current state, definition of done. Start here.
- [Agent Architecture](docs/architecture/AGENT-ARCHITECTURE.md) — agent contracts, budgets, memory tiers, tool standards, skill spec.
- [Reference Architecture](docs/architecture/REFERENCE-ARCHITECTURE.md) — Layered architecture across Control Plane, Orchestration, Agent Harness, Sandbox, and Data Plane.
- [Development Workflow](docs/DEVELOPMENT-WORKFLOW.md) — how a slice is planned, reviewed, verified and merged.
- [Antigravity Project Rules](docs/antigravity/ANTIGRAVITY-PROJECT-RULES.md) — Architectural boundaries, security rules, and engineering principles.
- [Archived: MVP Implementation Roadmap](docs/archive/MVP-IMPLEMENTATION-ROADMAP.md) — the superseded 19-phase sequence, kept as a map of scope. Not a plan; do not cite its phase numbers.

---

## Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI workflow (lint, test, build)
├── docs/
│   ├── antigravity/           # Engineering rules & step/slice tracker
│   ├── architecture/          # Reference & agent architecture
│   ├── archive/               # Superseded documents, kept for the record
│   ├── implementation/        # Slice breakdowns per step
│   └── requirements/          # MVP scope & functional requirements
├── infrastructure/
│   ├── docker-compose.yml     # Local PostgreSQL 17 & Redis services
│   └── .env.example
├── backend/
│   ├── .venv/                 # Python 3.13 virtual environment
│   ├── pyproject.toml         # Authoritative backend configuration & dependencies
│   ├── alembic/               # Async database migrations (baseline)
│   ├── app/
│   │   ├── core/              # Config, async database engine, error handling
│   │   ├── api/v1/            # Versioned API routes & health endpoints
│   │   └── main.py            # FastAPI entry point & CORS
│   └── tests/                 # Pytest test suite
├── frontend/
│   ├── package.json           # Next.js 16, TypeScript, Tailwind CSS, Vitest (pnpm)
│   ├── src/
│   │   ├── app/               # Next.js App Router (Fussion Studio shell)
│   │   ├── lib/               # API client
│   │   └── __tests__/         # Vitest component test suite
│   └── pnpm-lock.yaml
├── .gitignore
├── .env.example
└── README.md
```

---

## Prerequisites

- **Node.js**: `v20+` (tested with Node 25)
- **pnpm**: `10+` (single authoritative package manager for frontend)
- **Python**: `3.13` (CPython 3.13 with `uv`)
- **PostgreSQL**: `17` (local service or via Docker Compose)
- **Docker & Docker Compose** (optional for local infra)

---

## Local Development Setup

### 1. Clone & Configure Environment

```bash
# Clone the repository
git clone <repo-url> fussion
cd fussion

# Copy example environment files
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### 2. Infrastructure (Optional / Docker)

To run PostgreSQL 17 and Redis via Docker Compose:

```bash
docker compose -f infrastructure/docker-compose.yml up -d
```

### 3. Backend Setup (FastAPI + Python 3.13 venv)

```bash
cd backend

# Create virtual environment with Python 3.13
uv venv .venv --python 3.13

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Unix/macOS:
source .venv/bin/activate

# Install dependencies in editable mode
uv pip install -e ".[dev]"

# Run database migrations (Alembic baseline)
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend health endpoints:
- Root health check: `http://localhost:8000/health`
- Versioned API health: `http://localhost:8000/api/v1/health`
- Interactive Swagger docs: `http://localhost:8000/docs`

### 4. Frontend Setup (Next.js + Tailwind CSS)

```bash
cd frontend

# Install dependencies using pnpm
pnpm install

# Start Next.js development server
pnpm dev
```

Visit `http://localhost:3000` to view the Fussion Studio Foundation dashboard.

---

## Testing & Quality Checks

### Backend Checks

```bash
cd backend

# Run Ruff linter
.venv\Scripts\ruff check app tests

# Run Pytest suite
.venv\Scripts\pytest tests
```

### Frontend Checks

```bash
cd frontend

# Run Vitest unit tests
pnpm test

# Run Next.js production build & type check
pnpm build
```

---

## Database Strategy & Fallback Rules

- **PostgreSQL 17** is the primary system of record.
- In **development and testing environments**, if PostgreSQL credentials are not yet configured, an async **SQLite fallback** is enabled to ensure zero-friction setup.
- In **production environments (`APP_ENV=production`)**, silent fallback to SQLite is **strictly prohibited**; the backend fails loudly at startup if PostgreSQL is unavailable.

---

## Next Milestone

**Phase 02 — Backend Core & Identity**: Implementation of Users, Businesses (Tenants), Memberships, RBAC, and Authentication.
