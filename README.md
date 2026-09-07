# Fussion — AI Integration Engineer Platform

> Transform your website and company knowledge into an autonomous, branded AI assistant.

Fussion is an **AI Integration Engineer Platform**. Rather than providing a simplistic embed script, Fussion acts as an automated software engineer that connects to your repository, analyzes your frontend architecture and styling, produces an integration plan for human approval, and implements, tests, and verifies a knowledge-grounded assistant in an isolated sandbox.

---

## Current Status: Phase 01 Complete

- **Current Phase**: **Phase 01 — Repository & Development Foundation** (Done)
- **Next Phase**: **Phase 02 — Backend Core & Identity** (Pending explicit instruction)
- **Phase Tracking Matrix**: [docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md](docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md)

---

## System Architecture & Governance

Fussion follows the approved system architecture designed in **Phases 1–27**:

- [Reference Architecture](docs/architecture/REFERENCE-ARCHITECTURE.md) — Layered architecture across Control Plane, Orchestration, Agent Harness, Sandbox, and Data Plane.
- [MVP Implementation Roadmap](docs/implementation/MVP-IMPLEMENTATION-ROADMAP.md) — The locked 9-phase MVP milestone sequence.
- [Antigravity Project Rules](docs/antigravity/ANTIGRAVITY-PROJECT-RULES.md) — Architectural boundaries, security rules, and engineering principles.

---

## Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI workflow (lint, test, build)
├── docs/
│   ├── antigravity/           # Engineering rules & phase tracker
│   ├── architecture/          # Reference architecture synthesis
│   └── implementation/        # Locked MVP implementation roadmap
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
