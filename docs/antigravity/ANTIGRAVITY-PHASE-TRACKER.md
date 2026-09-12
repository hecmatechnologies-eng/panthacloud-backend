# Fussion — Phase & Slice Tracker

**How work is identified here (settled 2026-09-12).** New work is a **step and slice** — steps
A–D from `docs/FEASIBILITY.md` §3, sliced in `docs/implementation/STEP-<X>-SLICES.md`. The
current state of those is the *Step status* table below; each completed slice gets a log section
at the end of this file.

**The phase table below is the historical record of work done before that decision.** Its
numbers are not used for new work and must not be cited in a plan or a commit message. In
particular, legacy **"Phase B.1" is frontend authentication and is unrelated to step B slice
B1** — the collision that prompted this. The 19-phase `MVP-IMPLEMENTATION-ROADMAP.md` used a
third, different numbering and is archived under `docs/archive/`.

## Step status (current plan — `FEASIBILITY.md` §3)

| Step | Scope | Status |
| :--- | :--- | :--- |
| **A. Truth & safety** | layout-overwrite fix, workspace clone+read, one roadmap, key removal, 05–08 decision | **IN PROGRESS** — layout-overwrite fix (`415d5e3`), roadmap reconciliation (`17a9c79`) and dev-secret removal from source done. Remaining items and their triggers are tabled in `CLAUDE.md` §3: `@/` alias before B8, the 05–08 decision before step C, `SandboxProvider` with B5 or later, and the git-history rewrite before the first push |
| **B. Runtime plane** | `STEP-B-SLICES.md` B1–B8 | **IN PROGRESS** — B1 done (`f8cc086`); B2 next |
| **C. Analyst + harness + skills + evals** | WebsiteAnalyst, thin harness, tool gateway, 2 skill packages, 5-case eval corpus | NOT STARTED — no slice breakdown yet |
| **D. Coding agent** | write capability, generated-code scan, ChangeSet → PR, bounded repair | NOT STARTED — no slice breakdown yet |

## Phase history (legacy numbering — record only, never cited for new work)

| Phase | Description | Status | Started | Completed |
| :--- | :--- | :--- | :--- | :--- |
| **01** | **Repository & Development Foundation** | **COMPLETED** | 2026-09-07 | 2026-09-07 |
| **02** | **Backend Core & Identity** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **03** | **Project & Integration Management** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **04** | **Repository & Source Integration Management** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **05** | **Repository Acquisition & Source Inspection Foundation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **06** | **Contract & Architecture Discovery Foundation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **07** | **Contract Normalization & Integration Planning Foundation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **08** | **Integration Adapter & Execution Planning Foundation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **Phase A** | **MVP Realignment — Product & Architecture Reset** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **Phase B** | **MVP Realignment — Frontend Studio Restructuring & UX Architecture** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **Phase B.1** | **MVP Realignment — Frontend Authentication & Application Architecture Foundation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **09** | **Knowledge Base Foundation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **10** | **Assistant Configuration & Widget Generation** | **COMPLETED** | 2026-09-08 | 2026-09-08 |
| **11** | **Sandbox Integration & GitHub Pull Request** | **COMPLETED** | 2026-09-08 | 2026-09-12 |
| ~~12~~ | ~~Visitor Runtime & End-to-End MVP Validation~~ | **SUPERSEDED** by step B (`STEP-B-SLICES.md`) | - | - |

---

## Phase 01 Log

### Objective
Establish clean repository structure, Next.js frontend foundation, FastAPI backend foundation, database connectivity with PostgreSQL primary and dev/test SQLite fallback, environment configuration, testing, CI workflow, and project governance documentation.

### Completed Work
- **Repository & Governance**: Initialized Git repository, root `.gitignore`, created desktop directory junction for `fussion`, and authored foundational governance specifications (`ANTIGRAVITY-PROJECT-RULES.md`, `MVP-IMPLEMENTATION-ROADMAP.md`, `REFERENCE-ARCHITECTURE.md`, `ANTIGRAVITY-PHASE-TRACKER.md`, `README.md`).
- **Infrastructure**: Configured `infrastructure/docker-compose.yml` for PostgreSQL 17 and Redis services with health checks and volumes, plus environment example template.
- **Backend Foundation**:
  - FastAPI application structure (`backend/app/main.py`, `backend/app/core/`, `backend/app/api/v1/`).
  - Python 3.13 virtual environment (`backend/.venv`) with `pyproject.toml` as single authoritative dependency definition.
  - SQLAlchemy 2.0 async engine and session management with PostgreSQL primary connection and dev/test SQLite fallback.
  - Strict production enforcement preventing silent fallback to SQLite in production.
  - Alembic async database migration framework with baseline empty migration (`0001_initial_baseline.py`). No domain entities created.
  - Standardized JSON error handlers and configuration-driven CORS middleware.
  - Public `/health` and versioned `/api/v1/health` endpoints without leaking internal database metrics in production.
  - Pytest test suite (`test_health.py`, `conftest.py`) verifying health checks, error responses, and configuration enforcement.
  - Ruff linter check and format passed with 0 errors.
- **Frontend Foundation**:
  - Next.js 16 (App Router) + TypeScript + Tailwind CSS using `pnpm` as the sole authoritative package manager.
  - Client API service (`frontend/src/lib/api.ts`) connecting to FastAPI backend with environment configuration (`NEXT_PUBLIC_API_URL`).
  - Fussion Studio Foundation dashboard (`frontend/src/app/page.tsx`) rendering real-time operational status for Frontend, Backend, and Database.
  - Vitest + React Testing Library unit test suite (`frontend/src/__tests__/page.test.tsx`).
  - Next.js Turbopack production build verified cleanly.
- **CI Foundation**:
  - Configured GitHub Actions workflow (`.github/workflows/ci.yml`) covering backend linting, pytest, frontend vitest, and Next.js production build.
- **End-to-End Verification**:
  - Verified live backend server on port 8000 responding with 200 OK.
  - Verified live Next.js server on port 3000 rendering Fussion Studio dashboard.
  - Verified proof of Browser → Next.js → FastAPI → Database connectivity pipeline.

### Architectural & Technology Decisions
1. **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind CSS with `pnpm` (authoritative package manager).
2. **Backend**: FastAPI + Python 3.13 venv with `pyproject.toml` as single source of truth.
3. **Database**: PostgreSQL 17 as primary system of record via async SQLAlchemy 2.0. Async SQLite fallback enabled strictly for dev/test environments; production strictly fails loudly if PostgreSQL is absent.
4. **Domain Boundary**: Strict adherence to Phase 01 boundary—zero business domain entities (users, orgs, projects, etc.) created.
5. **Security**: Redacted database internal metrics on public `/health` endpoint; environment-driven CORS origins.

### Deviations
None. All implementations conform to Design Phases 1–27 and the Phase 01 Corrections addendum.

### Blockers
None.

---

## Phase 02 Log

### Objective
Establish the authoritative Control Plane identity and tenancy domain: `User` → `Organization` → `Membership` → `Project`, modern password hashing, JWT authentication, tenant resolution, RBAC authorization, and multi-tenant isolation.

### Completed Work
- **Security & Password Hashing**:
  - Modern `bcrypt` password hashing without relying on Python 3.13 deprecated standard library `crypt` / legacy `passlib`.
  - Minimal claim JWT access tokens signed with `PyJWT` (HS256).
  - Production security configuration requiring high-entropy `JWT_SECRET_KEY` and failing loudly on default or predictable secrets.
- **Domain Models (SQLAlchemy 2.0 Async)**:
  - `BaseModel`: Abstract model with UUID primary keys and UTC audit timestamps.
  - `User`: Email (unique, normalized), hashed password, full name, active/superuser flags, and membership relationship.
  - `Organization`: Primary tenant boundary with unique slug and cascading relationships to memberships and projects.
  - `Membership`: Connects User to Organization with `RoleEnum` (`OWNER`, `ADMIN`, `MEMBER`, `VIEWER`), unique constraint per `(user_id, organization_id)`.
  - `Project`: Organization-scoped entity with unique constraint per `(organization_id, slug)`.
- **RBAC & Authorization Matrix**:
  - Explicit permissions matrix (`org:view`, `org:delete`, `members:view`, `members:invite`, `members:role_change`, `members:remove`, `project:create`, `project:view`, `project:modify`).
  - Owner protection: Enforces that an organization must have at least one OWNER; the last OWNER cannot be demoted or removed.
  - Admin boundary: Administrators cannot assign the OWNER role or remove an OWNER.
- **Tenant Resolution & Dependencies**:
  - `get_current_user`: Bearer JWT token validation and user lookup.
  - `get_current_organization`: Scoped organization and membership lookup; returns 404 on unassociated organizations to prevent tenant enumeration.
  - `require_permission`: Factory dependency checking membership role against required operation permission.
  - `get_current_project`: Project resolution strictly scoped to the authenticated organization.
- **Endpoints**:
  - `POST /api/v1/auth/register`: Transactionally creates User, default personal Organization, and OWNER Membership.
  - `POST /api/v1/auth/login`: Constant-time password verification and token generation.
  - `GET /api/v1/auth/me`: Profile retrieval without leaking password hash.
  - `POST /api/v1/organizations`: Create new organization with creator as OWNER.
  - `GET /api/v1/organizations`: Membership-scoped organization listing.
  - `GET /api/v1/organizations/{org_id}`: Tenant-scoped organization retrieval.
  - `GET /api/v1/organizations/{org_id}/members`: List organization members.
  - `POST /api/v1/organizations/{org_id}/members`: Direct member invitation/creation (MVP simplification).
  - `PATCH /api/v1/organizations/{org_id}/members/{member_id}`: Member role update with owner protection.
  - `DELETE /api/v1/organizations/{org_id}/members/{member_id}`: Member removal with owner protection.
  - `POST /api/v1/organizations/{org_id}/projects`: Scoped project creation.
  - `GET /api/v1/organizations/{org_id}/projects`: Scoped project listing.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}`: Scoped project retrieval.
  - `PATCH /api/v1/organizations/{org_id}/projects/{project_id}`: Scoped project update.
- **Database Migrations**:
  - `backend/alembic/versions/0002_domain_core_identity.py` creating all four tables, foreign keys with cascading rules, indexes, and unique constraints.
  - Verified migration upgrade and downgrade execution cleanly.
- **Testing & Verification**:
  - 19 passed automated tests in `backend/tests/` covering authentication, token expiry, hashing, scoped organizations, RBAC permissions, owner protection, and project CRUD.
  - Mandatory Section 27 Critical Multi-Tenant Security Test passing: User A / Org A / Project A vs User B / Org B / Project B, including URL tampering rejection (returns 404).
  - Ruff linter check: 0 errors.

### Architectural & Technology Decisions
1. **Password Hashing**: Direct `bcrypt` hashing selected over legacy `passlib` to ensure full Python 3.13 compatibility without runtime warnings or deprecated C extensions.
2. **Tenant Resolution**: Organization is the primary tenant boundary. Sub-resources (memberships, projects) require validated membership in the parent organization. Cross-tenant access requests return 404 Not Found rather than 403 to prevent enumeration of existing cross-tenant resource IDs.
3. **Project Slug Scoping**: Unique constraint is scoped to `(organization_id, slug)`, enabling distinct organizations to maintain projects with identical human-readable slugs (e.g. `website`) without collision.
4. **Member Creation**: Direct member addition implemented as an approved MVP simplification prior to email invitation workflows in subsequent phases.
5. **Control Plane Boundary**: Zero runtime plane concepts (agents, sandboxes, tools, widgets, visitor sessions) were introduced, keeping identity and governance strictly separated.

### Deviations
None. All implementations conform to Design Phases 1–27 and the Phase 02 specification.

### Blockers
None.

---

## Phase 03 Log

### Objective
Extend the Project Control Plane so that a Fussion project becomes the authoritative container for external integrations and configuration: `Organization` → `Project` → `Integration`, provider model, encrypted credentials boundary, lifecycle management, RBAC, tenant isolation, and Studio UI integration.

### Completed Work
- **Integration Domain Model (SQLAlchemy 2.0 Async)**:
  - `Integration`: UUID primary key, project foreign key with cascading deletion, `IntegrationProvider` enum (`github`, `gitlab`, `external_api`, `webhook`), `IntegrationStatus` enum (`PENDING`, `ACTIVE`, `DISCONNECTED`, `ERROR`, `DISABLED`), JSON configuration, and encrypted credentials reference.
  - Project referential integrity and uniqueness constraint: `UNIQUE(project_id, name)`.
  - `Project.integrations` relationship with `cascade="all, delete-orphan"`.
- **Secret Storage Boundary**:
  - `SecretStore` abstraction using AES/Fernet encryption for credentials at rest (`app.core.secrets`).
  - Production security configuration with `effective_secret_encryption_key` enforcing high-entropy keys and preventing dev secret fallbacks in production.
  - Zero plaintext secrets stored in database columns; schemas strictly redact sensitive material (`has_credentials` boolean indicator).
- **RBAC & Authorization Extension**:
  - Permissions matrix updated with `PROJECT_DELETE`, `INTEGRATION_VIEW`, `INTEGRATION_CREATE`, `INTEGRATION_MODIFY`, and `INTEGRATION_DELETE`.
  - Enforced RBAC: Members can create/modify integrations; Admins and Owners can delete integrations and projects; Viewers have read-only access.
- **Tenant-Scoped Integration APIs**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/integrations`: Create integration with encrypted credential storage.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/integrations`: List integrations scoped to project.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/integrations/{integration_id}`: Retrieve integration with redacted credentials.
  - `PATCH /api/v1/organizations/{org_id}/projects/{project_id}/integrations/{integration_id}`: Update configuration, credentials, and status with lifecycle transition guards.
  - `DELETE /api/v1/organizations/{org_id}/projects/{project_id}/integrations/{integration_id}`: Delete integration.
  - `DELETE /api/v1/organizations/{org_id}/projects/{project_id}`: Delete project with cascading integration deletion.
- **Database Migrations**:
  - `backend/alembic/versions/0003_project_integrations.py` creating the `integrations` table with constraints and foreign keys.
  - Verified upgrade and downgrade execution cleanly.
- **Frontend Studio Workspace**:
  - Extended typed API client (`frontend/src/lib/api.ts`) with `projectsApi` and `integrationsApi`.
  - Added functional Project and Integration workspace manager in `frontend/src/app/page.tsx` with project selection, integration connection modal, and live status badges.
- **Testing & Verification**:
  - Backend pytest suite: 25 / 25 passed in 13.17s (all Phase 01, Phase 02, and Phase 03 tests green).
  - Mandatory Section 19 Multi-Tenant Integration Security Test passing: User A / Org A / Proj A / Integ A vs User B / Org B / Proj B / Integ B, including URL tampering rejection (returns 404).
  - Ruff linter check: 0 errors.
  - Frontend Vitest suite: 1 passed (1).
  - Next.js Turbopack production build: 0 errors.

### Architectural & Technology Decisions
1. **Encrypted Secret Boundary**: Authenticated encryption (`Fernet`) encapsulates integration credentials, ensuring database dumps or backups never expose plaintext provider tokens.
2. **Provider Representation**: Explicit `IntegrationProvider` enum representation combined with structured configuration dictionary avoids premature abstract class hierarchies while supporting multiple distinct integrations per provider.
3. **Integration Uniqueness**: Scoped to `UNIQUE(project_id, name)` to permit a project to connect multiple integrations for the same provider (e.g. frontend repo vs documentation repo).
4. **Lifecycle State Transitions**: Validated state machine enforces transitions from user action (e.g. `PENDING` → `ACTIVE`, `ACTIVE` → `DISCONNECTED`), rejecting invalid state changes.
5. **Control Plane Boundary**: Zero runtime execution, agents, sandboxes, MCP, or repository indexing were introduced, strictly preserving Control Plane purity.

### Deviations
None. All implementations conform to Design Phases 1–27 and the Phase 03 specification.

### Blockers
None.

---

## Phase 04 Log

### Objective
Establish the authoritative Control Plane representation for external source repositories connected to Fussion projects via integrations: `Project` → `Integration` → `Repository`, provider compatibility, external identity constraints, repository lifecycle state, RBAC authorization, multi-tenant isolation, and Studio UI integration.

### Completed Work
- **Repository Domain Model (SQLAlchemy 2.0 Async)**:
  - `Repository`: UUID primary key, `project_id` foreign key (`ondelete="CASCADE"`), `integration_id` foreign key (`ondelete="CASCADE"`), `provider` enum (`github`, `gitlab`), `status` enum (`PENDING`, `CONNECTED`, `DISCONNECTED`, `ERROR`), `name`, `full_name`, `external_id`, `default_branch`, `url`, and JSON `metadata`.
  - External identity constraint: `UNIQUE(integration_id, external_id)`.
  - Relationships: `Project.repositories` and `Integration.repositories` both with `cascade="all, delete-orphan"`.
- **RBAC & Authorization Matrix**:
  - Permissions matrix updated with `REPOSITORY_VIEW`, `REPOSITORY_CREATE`, `REPOSITORY_MODIFY`, and `REPOSITORY_DELETE`.
  - Role enforcement: OWNER & ADMIN have all repository capabilities; MEMBER can view, create, and modify metadata/status; VIEWER has read-only access.
- **Tenant Resolution & Dependencies**:
  - `get_current_repository` dependency enforcing the complete resolution chain: `User` → `Organization Membership` → `Project in Org` → `Repository in Project` → `Permission.REPOSITORY_VIEW`.
  - Non-enumerating 404 returned on missing resources, cross-project, or cross-tenant access.
- **Provider & Integration Compatibility Validation**:
  - `POST` endpoint verifies that the integration belongs strictly to the project (`integration.project_id == project.id`).
  - Provider compatibility enforced: repository provider must match integration provider (`github` + `github` valid, `github` + `gitlab` rejected with 400).
- **Repository API Endpoints**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories`: Register repository (defaults to `PENDING` status without falsely asserting external connectivity).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories`: List repositories scoped to project.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}`: Retrieve repository details with safe metadata.
  - `PATCH /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}`: Update metadata, branch, and status with validated lifecycle transitions.
  - `DELETE /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}`: Delete repository.
- **Database Migration**:
  - `backend/alembic/versions/0004_repositories.py`: Created `repositories` table, foreign keys with cascade deletions, unique constraint `uq_repository_integration_external_id`, and indexes.
  - Verified upgrade and downgrade cycles cleanly.
- **Frontend Studio UI & API Client**:
  - Extended typed client (`frontend/src/lib/api.ts`) with `RepositoryProvider`, `RepositoryStatus`, `Repository`, `CreateRepositoryInput`, and `repositoriesApi`.
  - Enhanced Studio workspace in `frontend/src/app/page.tsx` with a Source Repositories section, status badges, branch indicators, and a Register Repository modal requiring an active integration.
- **Automated Testing & Verification**:
  - `backend/tests/test_repositories.py`: 8 comprehensive tests covering CRUD, provider compatibility validation, integration project scoping, duplicate external ID rejection, status transitions, RBAC enforcement, Section 15/20 multi-tenant isolation, and cascade deletion from projects and integrations.
  - Full backend test suite: **33 / 33 passed** in 34.95s.
  - Ruff linter: **0 errors** (`All checks passed!`).
  - Frontend Vitest: **1 / 1 passed**.
  - Next.js Turbopack build: Compiled cleanly with zero errors.

### Architectural & Technology Decisions
1. **Source vs Repository Abstraction**: Neither Design Phases 1–27 nor `MVP-IMPLEMENTATION-ROADMAP.md` require a distinct abstract `Source` entity at this phase. Applying strict YAGNI, external Git sources are directly represented via the `Repository` entity linked to `Project` and `Integration`.
2. **Stable External Identity**: Enforced `UNIQUE(integration_id, external_id)` because repository names and URLs can change externally, whereas provider IDs provide immutable external identity.
3. **Provider Compatibility**: Domain-level validation enforces that the repository provider matches the integration provider without issuing unnecessary external network requests during registration.
4. **Lifecycle State Integrity**: Initial repository state defaults to `PENDING` rather than falsely asserting connectivity before Phase 05 inspection takes place. Valid lifecycle state machine enforces transitions (`PENDING`, `CONNECTED`, `DISCONNECTED`, `ERROR`).
5. **Cascading Referential Integrity**: Both `Project` deletion and `Integration` deletion cascade to child `Repository` records at the database level (`ondelete="CASCADE"`) and ORM level (`cascade="all, delete-orphan"`).
6. **Strict Control Plane Separation**: Zero Phase 05+ capabilities (cloning, sandbox execution, code analysis, AST parsing, MCP, agent harness/runtime, deployment) were introduced.

### Deviations
None. All implementations conform to Design Phases 1–27 and the locked Phase 04 prompt.

### Blockers
None.

---

## Phase 05 Log

### Objective
Establish the controlled, isolated, deterministic source acquisition and read-only inspection foundation for Fussion:
`Repository` → `Acquisition` → `Isolated Workspace` → `Safe Source Inspection` → `Deterministic Structured Metadata`.

### Completed Work
- **Core Configuration & Limits**:
  - `WORKSPACE_BASE_DIR` (`./data/workspaces`), `MAX_REPOSITORY_SIZE_MB` (250MB), `MAX_FILE_SIZE_MB` (10MB), `MAX_FILE_COUNT` (10,000), `MAX_DIRECTORY_DEPTH` (20), `ACQUISITION_TIMEOUT_SECONDS` (60s), `INSPECTION_TIMEOUT_SECONDS` (30s), `WORKSPACE_RETENTION_HOURS` (24h).
- **Domain Models & Enums**:
  - `SnapshotStatus`: `PENDING`, `ACQUIRING`, `READY`, `FAILED`, `EXPIRED`, `DELETED`.
  - `RepositorySnapshot`: UUID primary key, `repository_id` foreign key (`ondelete="CASCADE"`), `branch`, immutable `commit_sha` (40-char hex string), `status`, `workspace_reference` (opaque token `ws-<hex>`, never leaking physical path), `acquired_at`, `completed_at`, `error_code`, `error_message`, and JSON `metadata_`.
  - `AuditEvent`: Scoped event log tracking lifecycle actions (`repository.snapshot.created`, `repository.snapshot.acquisition_started`, `repository.snapshot.completed`, `repository.snapshot.failed`, `repository.inspection.completed`) with automatic redaction of secret tokens.
  - `Repository.snapshots`: Added relationship with `cascade="all, delete-orphan"`.
- **Database Migration**:
  - `backend/alembic/versions/0005_repository_snapshots.py`: Created `repository_snapshots` and `audit_events` tables, foreign keys with cascade rules, and indexes. Verified upgrade and downgrade cycles cleanly.
- **Isolated Workspace Manager (`WorkspaceManager`)**:
  - Tenant-isolated filesystem allocation: `{WORKSPACE_BASE_DIR}/{org_id}/{project_id}/{snapshot_id}`.
  - Opaque workspace references (`ws-<hex>`) preventing physical filesystem directory disclosure.
  - `assert_path_contained`: Enforces `realpath` directory containment and rejects directory traversal (`../`) and external symlink escapes.
  - `check_workspace_limits`: Validates directory depth, file count, per-file size, and cumulative repository size against security bounds.
  - `cleanup_workspace`: Safe teardown handling read-only Git objects on Windows (`os.chmod(path, 0o777)`).
- **Controlled Acquisition Service (`RepositoryAcquisitionService`)**:
  - Controlled Git acquisition via `asyncio.create_subprocess_exec` using `git clone --depth 1 --branch <branch> <url> <workspace_path>` (no shell expansion).
  - Cross-platform URL resolution handling HTTPS, Git, and local `file://` URLs for offline/fixture execution.
  - Post-acquisition immutable commit SHA binding via `git rev-parse HEAD`.
  - Safe credential handling: Injected access tokens sanitized from stderr/stdout with `[REDACTED]`; audit events stripped of credential keys.
  - Workspace limit validation immediately post-acquisition; clean workspace deletion upon limit violation, timeout, or failure.
- **Deterministic Inspection Service (`RepositoryInspectionService`)**:
  - Read-only, deterministic filesystem traversal.
  - Extension-based language detection (.py, .ts, .tsx, .js, .jsx, .go, .rs, .java, .php, .rb, .cs, .cpp, .c, .h).
  - Manifest file detection (`package.json`, `pnpm-lock.yaml`, `pyproject.toml`, `requirements.txt`, `composer.json`, `go.mod`, `Cargo.toml`, etc.).
  - Static manifest content heuristics for framework detection: Next.js, React, Express, NestJS, FastAPI, Django, Laravel.
  - API contract detection (`openapi.yaml`, `swagger.json`, etc.) and deployment files (`Dockerfile`, `docker-compose.yml`).
  - Idempotent and reproducible results verified across multiple inspection runs.
- **RBAC & Authorization Matrix**:
  - Permissions matrix updated with `REPOSITORY_SNAPSHOT_VIEW`, `REPOSITORY_SNAPSHOT_CREATE`, and `REPOSITORY_INSPECT`.
  - Role enforcement: OWNER & ADMIN have full snapshot and inspection capabilities; MEMBER can acquire and inspect; VIEWER has read-only access (403 on acquire/inspect).
- **Tenant Resolution & Dependencies**:
  - `get_current_snapshot`: Enforces complete hierarchy: `User` → `Organization Membership` → `Project` → `Repository` → `Snapshot`. Non-enumerating 404 returned on cross-tenant, cross-project, or cross-repository access.
- **API Endpoints**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots`: Acquire snapshot.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots`: List snapshots.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}`: Get snapshot.
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/inspect`: Perform deterministic safe inspection.
- **Automated Test Suite**:
  - `backend/tests/test_snapshots_inspection.py`: 10 comprehensive tests covering commit SHA binding, deterministic inspection, Django/React detection, failed acquisition lifecycle, workspace containment, symlink escape rejection, resource limits, credential redaction, multi-tenant isolation (Section 15/20/27), and RBAC enforcement.
  - Full backend regression test suite: **43 / 43 passed** in 57.12s.
  - Ruff linter: **0 errors** (`All checks passed!`).
- **Frontend Studio UI & API Client**:
  - Extended typed client (`frontend/src/lib/api.ts`) with `SnapshotStatus`, `RepositorySnapshot`, `InspectionResult`, `CreateSnapshotInput`, and `snapshotsApi`.
  - Studio dashboard updated with acquired snapshots sub-list, "Acquire Snapshot" button/modal, and "Safe Deterministic Source Inspection" findings panel displaying languages, frameworks, manifests, contracts, deployment files, and filesystem structure metrics.
  - Static inspection invariant disclaimer prominently displayed.
  - Vitest test suite: **1 / 1 passed**.
  - Next.js Turbopack build: Compiled successfully with zero errors.

### Architectural & Technology Decisions
1. **Deterministic Static Inspection Over Dynamic Execution**: Phase 05 strictly performs static, read-only inspection. No language interpreters (`python`, `node`), package managers (`pip`, `npm`), or compilers are ever invoked against repository code.
2. **Immutable Commit Binding**: Every snapshot strictly binds the 40-character commit SHA determined via `git rev-parse HEAD` immediately after shallow clone, ensuring downstream phases analyze immutable revisions.
3. **Workspace Isolation & Path Containment**: Physical paths use opaque references (`ws-<hex>`) in public APIs. All path resolution is verified with `assert_path_contained`, preventing directory traversal and symlink escapes outside the tenant workspace boundary.
4. **Zero Credential Exposure**: Tokens are injected solely at subprocess invocation, Git stderr/stdout is sanitized with regex-based redaction, and audit event payloads explicitly strip all credential keys.
5. **Strict Scope Invariant**: Zero AI/LLM models, agent harness, MCP servers, or code execution tools were introduced in Phase 05.

### Deviations
None. All implementations conform to Design Phases 1–27 and the locked Phase 05 prompt.

### Blockers
None.

---

## Phase 06 Log

### Objective
Build a deterministic, static, read-only, evidence-backed discovery layer that analyzes an acquired `RepositorySnapshot` workspace and produces a structured architectural representation bound to the exact immutable commit SHA. Extracts frameworks, entrypoints, API contracts (OpenAPI/Swagger), static routes, declared dependencies, architectural modules, configuration boundaries (with sensitive configs masked), and deployment files.

### Completed Work
- **Dependencies**: Added `pyyaml>=6.0.0` to `backend/pyproject.toml` for safe YAML contract parsing (`yaml.safe_load`).
- **Domain Models & Enums**:
  - `DiscoveryStatus`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`.
  - `DiscoveryRun`: UUID primary key, `snapshot_id` foreign key (`ondelete="CASCADE"`), `status`, `started_at`, `completed_at`, `error_code`, `error_message`, and JSON `metadata_`.
  - `RepositorySnapshot.discovery_runs`: Added relationship with `cascade="all, delete-orphan"`.
- **Database Migration**:
  - `backend/alembic/versions/0006_discovery.py`: Created `discovery_runs` table, snapshot foreign key with cascade, status enum, and index on `snapshot_id`. Tested upgrade/downgrade cleanly.
- **Pydantic Schemas**:
  - `Evidence`: `file` (relative repo path), `reason`, optional `line` and `symbol`.
  - Findings: `FrameworkFinding`, `EntrypointFinding`, `RouteFinding`, `ApiContractFinding`, `DependencyFinding`, `ModuleFinding`, `ConfigurationFinding`, `DeploymentFinding`.
  - `DiscoveryResult`: Complete architectural fact model tied to `snapshot_id` and `commit_sha`.
  - `DiscoveryCreate`, `DiscoveryRead` (using `ConfigDict(from_attributes=True)`).
- **RBAC & Authorization Matrix**:
  - Added permissions: `REPOSITORY_DISCOVERY_VIEW = "repository:discovery:view"` and `REPOSITORY_DISCOVERY_CREATE = "repository:discovery:create"`.
  - Role mapping: OWNER, ADMIN, and MEMBER have create and view; VIEWER has read-only access (403 on create).
- **Tenant Resolution & Dependencies**:
  - `get_current_discovery`: Validates full containment hierarchy `User` → `Organization Membership` → `Project` → `Repository` → `RepositorySnapshot` → `DiscoveryRun`. Returns 404 on cross-tenant access to prevent enumeration.
- **Static Discovery Service (`RepositoryDiscoveryService`)**:
  - Snapshot readiness check: Strictly enforces `snapshot.status == READY`.
  - Workspace containment: Enforces `workspace_manager.assert_path_contained`, rejecting traversal and symlink escapes.
  - Framework detection: Python (FastAPI, Flask, Django), Node/JS/TS (Next.js, React, Express, NestJS), PHP (Laravel) with evidence files and line reasons.
  - Entrypoint detection: Static regex AST parsing for application instances (`FastAPI(...)`, `Flask(...)`, `manage.py`, `express()`, `NestFactory.create(...)`, Next.js routed pages).
  - API Contracts: Safe parsing of OpenAPI 3.x and Swagger 2.0 specs. Extracts operations, paths, titles, versions, and servers. Resilient syntax error handling (`status="INVALID"`) without failing the discovery run.
  - Static Route detection: Extracts `@app.get`, `@router.post`, Flask `@route`, Django `path(...)`, Express `app.get(...)` with method, path, handler name, source line, and evidence.
  - Declared Dependencies: Manifest parsing for `pyproject.toml` (PEP 621 & Poetry), `requirements.txt`, `package.json`, `composer.json`, `Cargo.toml`.
  - Modules: Structural module detection (`api`, `data_models`, `services`, `ui_components`, `utilities`) with predominant language and child counts.
  - Configuration Boundaries: Categorizes tooling, linter, testing, styling, and database configs. Identifies `.env` files with `sensitive=True` while strictly redacting/masking values from metadata.
  - Deployment structures: `Dockerfile`, `docker-compose.yml`, GitHub Actions workflows, `Procfile`, `fly.toml`, `vercel.json`.
  - Determinism guarantee: All findings lists are sorted by immutable keys (names, paths, methods, lines) ensuring 100% reproducible results against identical snapshot commits.
  - Audit logging: Records `repository.discovery.started`, `repository.discovery.completed`, and `repository.discovery.failed` events.
- **API Endpoints**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/discoveries`: Trigger discovery.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/discoveries`: List discovery runs.
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/discoveries/{discovery_id}`: Retrieve discovery run findings.
- **Automated Test Suite**:
  - `backend/tests/test_discovery.py`: 10 comprehensive tests covering discovery lifecycle, commit SHA binding, framework detection, entrypoints, valid/invalid API contracts, static route extraction, declared dependencies, sensitive configuration masking, run-to-run determinism, tenant isolation anti-enumeration (404), and RBAC enforcement.
  - Full backend test suite: **53 / 53 passed** in 92.31s with zero regressions.
  - Ruff linter: **0 errors** (`All checks passed!`).
- **Frontend Studio UI & Client**:
  - Typed client in `frontend/src/lib/api.ts` with `discoveriesApi`, `DiscoveryRun`, `DiscoveryResult`, and all finding types.
  - Fussion Studio dashboard (`frontend/src/app/page.tsx`) enhanced with "Discover" action button on snapshots and full "Contract & Architecture Fact Model" visualization panel with tabs for Overview, Frameworks, Entrypoints, Routes, API Contracts, Dependencies, Modules, Configs, and Deployment.
  - Prominent static discovery guarantee disclaimer displayed.
  - Vitest test suite: **1 / 1 passed**.
  - Next.js Turbopack production build: Compiled successfully with zero errors.

### Architectural & Technology Decisions
1. **Static Discovery Boundary**: Zero dynamic execution, zero subprocess execution of repository code, zero package installation, and zero AI/LLM tokens consumed. Untrusted repository files remain inert, static data.
2. **Commit SHA Immutability**: Discovery runs are bound to the immutable 40-character commit SHA of the acquired snapshot.
3. **100% Deterministic Reproducibility**: All findings lists are sorted deterministically before persistence, guaranteeing identical metadata outputs across multiple runs on the same commit SHA.
4. **Resilient OpenAPI Parsing**: Malformed API contracts are flagged with `status="INVALID"` and specific error diagnostics without aborting or crashing the discovery run.
5. **Zero Credential Exposure**: Sensitive configurations (`.env`, `.env.*`) are classified with `sensitive=True` and their contents are never read, parsed, or serialized into discovery metadata or logs.

### Deviations
None. All implementations conform to Design Phases 1–27 and the locked Phase 06 prompt.

### Blockers
None.

---

## Phase 07 Log

### Objective
Transform the deterministic architectural findings produced by Phase 06 into a normalized, evidence-backed API contract representation and an explicit integration planning model:
1. Canonical API contract and operation normalization resolving local `$ref` pointers while strictly rejecting remote/external refs.
2. Deterministic 4-bucket route reconciliation between documented API specifications and statically discovered routes (`MATCHED`, `DOCUMENTED_ONLY`, `IMPLEMENTED_ONLY`, `CONFLICT`).
3. Evidence-backed integration planning categorizing dependencies into standard cloud/runtime services (PostgreSQL, Redis, Stripe, S3, etc.).
4. Configuration and credential safety cataloging required variable names (`DATABASE_URL`, `STRIPE_SECRET_KEY`) with `sensitive=True`, with a strict guarantee that zero secret values are ever read, stored, or logged.
5. Interactive Studio UI visualization with reconciliation matrix cards, operation breakdowns, candidate services, credential safety tables, and unresolved questions.

### Completed Work
- **Domain Models (SQLAlchemy 2.0 Async)**:
  - `ContractStatus`: `DRAFT`, `NORMALIZED`, `RECONCILED`, `FAILED`.
  - `ContractSource`: `OPENAPI_SPEC`, `DISCOVERED_ROUTES`, `HYBRID`.
  - `ApiContract`: Primary key UUID, `snapshot_id` foreign key (`ondelete="CASCADE"`), `status`, `source`, `version`, `title`, `description`, `raw_spec_path`, `canonical_routes` (JSON), `auth_schemes` (JSON), `schemas` (JSON), `reconciliation` (JSON), `metadata_` (JSON), UTC audit timestamps.
  - `ApiOperation`: Primary key UUID, `contract_id` foreign key (`ondelete="CASCADE"`), `method`, `path`, `canonical_path`, `operation_id`, `summary`, `description`, `parameters` (JSON), `request_body` (JSON), `responses` (JSON), `auth_required` (boolean), `tags` (JSON), UTC audit timestamps.
  - `IntegrationPlanStatus`: `DRAFT`, `ANALYZED`, `READY`, `FAILED`.
  - `IntegrationPlan`: Primary key UUID, `project_id` foreign key (`ondelete="CASCADE"`), `discovery_id` foreign key (`ondelete="SET NULL"`), `status`, `title`, `description`, `candidates` (JSON), `required_credentials` (JSON), `unresolved_questions` (JSON), `metadata_` (JSON), UTC audit timestamps.
  - Cascading relationships added to `RepositorySnapshot`, `Project`, and `DiscoveryRun`.
- **Database Migrations**:
  - `backend/alembic/versions/0007_contracts.py` creating `api_contracts`, `api_operations`, and `integration_plans` tables with foreign keys, cascading delete rules, indexes, and status enums. Verified clean `upgrade head` and `downgrade -1`.
- **Pydantic Schemas**:
  - Contracts: `AuthenticationScheme`, `ReconciliationFinding`, `ContractReconciliation`, `ApiOperationRead`, `ApiContractRead`, `ContractCreate`.
  - Integration Plans: `IntegrationCandidate`, `RequiredCredential`, `UnresolvedQuestion`, `IntegrationPlanRead`, `IntegrationPlanCreate`.
- **RBAC & Authorization Matrix**:
  - Added permissions: `CONTRACT_VIEW = "contract:view"`, `CONTRACT_CREATE = "contract:create"`, `INTEGRATION_PLAN_VIEW = "integration_plan:view"`, `INTEGRATION_PLAN_CREATE = "integration_plan:create"`.
  - OWNER, ADMIN, and MEMBER roles have all 4 permissions; VIEWER has read-only access (403 Forbidden on create).
- **Tenant Resolution & Security Dependencies**:
  - `get_current_contract`: Strict containment validation `User` → `Organization Membership` → `Project` → `Repository` → `RepositorySnapshot` → `ApiContract`. Returns 404 Not Found on cross-tenant access to prevent resource enumeration.
  - `get_current_integration_plan`: Strict containment validation `User` → `Organization Membership` → `Project` → `IntegrationPlan`. Returns 404 Not Found on cross-tenant access.
- **Contract Normalization Service (`ContractNormalizationService`)**:
  - Workspace path validation: Enforces `workspace_manager.assert_path_contained` preventing path traversal.
  - Path canonicalization: Maps Express (`:id`), Django/Flask (`<id>`, `<int:id>`), and OpenAPI (`{id}`) path formats to unified `{id}` parameter format with lowercased HTTP methods.
  - Local `$ref` resolution: Recursively resolves in-document JSON pointers (e.g. `#/components/schemas/User`), detects and breaks cyclic references, and strictly rejects remote network URIs (`http://`, `https://`) and external files.
  - 4-Bucket Route Reconciliation:
    - `MATCHED`: Route documented in spec and discovered in static code with matching method and canonical path.
    - `DOCUMENTED_ONLY`: Route in spec but absent from static route discovery.
    - `IMPLEMENTED_ONLY`: Route implemented in code but absent from formal API specification.
    - `CONFLICT`: Route exists in both but exhibits parameter or signature discrepancies.
  - Audit logging: Records `contract.normalization.started`, `contract.normalization.completed`, and `contract.normalization.failed` events.
- **Integration Planning Service (`IntegrationPlanningService`)**:
  - `DEPENDENCY_CATALOG`: Deterministic mapping identifying candidate services across databases (PostgreSQL, MySQL, SQLite, MongoDB), caching (Redis, Memcached), messaging (RabbitMQ, Kafka, Celery), payments (Stripe), cloud storage (AWS S3, Google Cloud Storage), and auth (Supabase, Auth0).
  - Variable name extraction: Identifies required configuration keys (`DATABASE_URL`, `STRIPE_SECRET_KEY`, etc.) with `sensitive=True`.
  - Credential Safety Invariant: **Strictly zero secret values are ever read, stored, serialized, or logged**. Only variable names and redacted placeholders are handled.
  - Unresolved Questions: Generates structured questions with evidence and risk ratings when architectural configurations or critical credentials are unconfigured.
  - Audit logging: Records `integration_plan.started`, `integration_plan.completed`, and `integration_plan.failed` events.
- **API Endpoints**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/contracts`: Trigger normalization & reconciliation (201 Created).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/contracts`: List contracts (200 OK).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/contracts/{contract_id}`: Retrieve contract and operations (200 OK).
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/integration-plans`: Generate integration plan (201 Created).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/integration-plans`: List integration plans (200 OK).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/integration-plans/{plan_id}`: Retrieve integration plan (200 OK).
- **Automated Test Suite**:
  - `backend/tests/test_contracts.py`: 8 comprehensive tests covering OpenAPI normalization, local `$ref` resolution, circular reference handling, remote ref rejection, 4-bucket reconciliation (`MATCHED`, `DOCUMENTED_ONLY`, `IMPLEMENTED_ONLY`, `CONFLICT`), tenant isolation (404), and RBAC enforcement.
  - `backend/tests/test_integration_plans.py`: 5 comprehensive tests covering candidate inference from discoveries, credential safety (zero secret values stored), unresolved questions generation, tenant isolation (404), and RBAC enforcement.
  - Full backend test suite: **66 / 66 passed** in 88.66s with zero regressions.
  - Ruff linter: **0 errors** (`All checks passed!`).
- **Frontend Studio UI & Client**:
  - Typed client in `frontend/src/lib/api.ts` with `contractsApi`, `integrationPlansApi`, and all domain types.
  - Interactive normalization & plan generation buttons with loading states.
  - Contract Normalization & Route Reconciliation Studio panel with 4-bucket summary stat cards, findings list, normalized operations table, authentication schemes badges, and data schemas JSON viewer.
  - Integration Planning & Credential Safety Studio panel with candidate service cards, required credentials table (with explicit "VALUE CONCEALED" security badges and zero secret entry fields), and unresolved architectural questions with severity badges.
  - Frontend Vitest unit tests: **1 / 1 passed**.
  - Frontend Next.js production build: Compiled cleanly with zero errors.

### Architectural & Technology Decisions
1. **Deterministic Static Normalization**: Zero dynamic execution, zero subprocess execution of repository code, zero package installation, and zero AI/LLM tokens consumed.
2. **Local Reference Resolution & Remote Ref Refusal**: Local JSON pointers (`#/components/...`) are resolved to self-contained schemas with cycle detection. Any attempt to reference remote HTTP/HTTPS URLs or external file paths is rejected to prevent SSRF and out-of-boundary access.
3. **Canonical Path Matching**: Normalizes distinct route parameter notations (`:id`, `<int:id>`, `{id}`) into canonical `{id}` format, enabling accurate 4-bucket reconciliation between different web frameworks and OpenAPI specifications.
4. **Credential Safety Invariant**: Under no circumstance are secret or configuration values read from `.env` files or workspaces, saved to the database, or transmitted to the client. Only parameter keys (e.g. `DATABASE_URL`) and redacted indicators are captured.
5. **Strict Scope Boundary**: Zero AI/LLM models, agent harness, MCP generation, or tool registries were introduced in Phase 07.

### Deviations
None. All implementations conform to Design Phases 1–27 and the Phase 07 specification.

### Blockers
None.

---

## Phase 08 Log

### Objective
Transform the candidate integrations and normalized API contracts from Phase 07 into declarative, evidence-backed integration adapters and safe, deterministic execution plans:
1. Declarative integration adapters across standard system categories: `DATABASE`, `CACHE`, `PAYMENT`, `STORAGE`, `WEBHOOK`, `MESSAGE_BROKER`, `AUTHENTICATION`, `EXTERNAL_SERVICE`, and `UNKNOWN`.
2. Safe execution planning with deterministic step IDs (`step-1`, `step-2`, ...), explicit prerequisite DAG dependencies (`depends_on`), safety classifications (`CONFIGURATION`, `READ_ONLY`, `WRITE`, `DESTRUCTIVE`, `EXTERNAL_NETWORK`, `CREDENTIAL_REQUIRED`), and approval boundaries.
3. Strict non-execution invariant: External actions marked `BLOCKED` with explicit blocked reasons. Zero external systems contacted, zero repository code executed.
4. Credential safety invariant: Only configuration variable names cataloged (`sensitive=True`), strictly zero secret values read, stored, or logged.
5. Multi-tenant isolation and RBAC: OWNER/ADMIN/MEMBER can create and view, VIEWER can view only (403 Forbidden on create). Cross-tenant access returns 404 Not Found to prevent resource enumeration.
6. Interactive Studio UI: Planned Adapters and Deterministic Execution Plan panels with safety badges, explicit blocked boundaries, and strictly NO execute button.

### Completed Work
- **Domain Models (SQLAlchemy 2.0 Async)**:
  - `AdapterStatus`: `PLANNED`, `CONFIGURED`, `READY`, `DISABLED`, `REVIEW_REQUIRED`, `DEPRECATED`.
  - `AdapterType`: `DATABASE`, `CACHE`, `PAYMENT`, `STORAGE`, `WEBHOOK`, `MESSAGE_BROKER`, `AUTHENTICATION`, `EXTERNAL_SERVICE`, `UNKNOWN`.
  - `IntegrationAdapter`: Primary key UUID, `snapshot_id` foreign key (`ondelete="CASCADE"`), `integration_plan_id` foreign key (`ondelete="SET NULL"`), `project_id` foreign key (`ondelete="CASCADE"`), `name`, `adapter_type`, `provider`, `status`, `operations` (JSON), `configuration` (JSON), `required_credentials` (JSON), `metadata_` (JSON), UTC audit timestamps.
  - `ExecutionPlanStatus`: `DRAFT`, `READY`, `REQUIRES_APPROVAL`, `BLOCKED`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`.
  - `ExecutionPlan`: Primary key UUID, `snapshot_id` foreign key (`ondelete="CASCADE"`), `integration_plan_id` foreign key (`ondelete="SET NULL"`), `project_id` foreign key (`ondelete="CASCADE"`), `name`, `status`, `version`, `steps` (JSON), `blocked_reasons` (JSON), `metadata_` (JSON), UTC audit timestamps.
  - Relationships added to `IntegrationPlan`, `RepositorySnapshot`, and `Project`.
- **Database Migrations**:
  - `backend/alembic/versions/0008_integration_adapters.py` creating `integration_adapters` and `execution_plans` tables with foreign keys, cascading delete rules, indexes, and status enums. Verified clean `upgrade head`, `downgrade -1`, and `upgrade head`.
- **Pydantic Schemas**:
  - Integration Adapters: `AdapterOperation`, `AdapterConfiguration`, `IntegrationAdapterCreate`, `IntegrationAdapterRead`.
  - Execution Plans: `SafetyClassification`, `ExecutionStep`, `ExecutionPlanCreate`, `ExecutionPlanRead`.
- **RBAC & Authorization Matrix**:
  - Added permissions: `INTEGRATION_ADAPTER_VIEW = "integration_adapter:view"`, `INTEGRATION_ADAPTER_CREATE = "integration_adapter:create"`, `EXECUTION_PLAN_VIEW = "execution_plan:view"`, `EXECUTION_PLAN_CREATE = "execution_plan:create"`.
  - OWNER, ADMIN, and MEMBER roles have all 4 permissions; VIEWER has read-only access (403 Forbidden on create).
- **Tenant Resolution & Security Dependencies**:
  - `get_current_integration_adapter`: Strict containment validation `User` → `Organization Membership` → `Project` → `Repository` → `RepositorySnapshot` → `IntegrationAdapter`. Returns 404 Not Found on cross-tenant access to prevent resource enumeration.
  - `get_current_execution_plan`: Strict containment validation `User` → `Organization Membership` → `Project` → `Repository` → `RepositorySnapshot` → `ExecutionPlan`. Returns 404 Not Found on cross-tenant access.
- **Integration Adapter Planning Service (`IntegrationAdapterPlanningService`)**:
  - Maps Phase 07 candidates to concrete adapter types.
  - Generates standard operations (`CONNECT`, `DISCONNECT`, `HEALTHCHECK`, `EXECUTE`, `CHARGE`, `REFUND`, `STORE`, `RETRIEVE`, `RECEIVE`).
  - Classifies webhooks detected from route discovery into `WEBHOOK` adapters with `RECEIVE` operations.
  - Classifies unrecognized dependencies into `UNKNOWN` adapters with `status = "REVIEW_REQUIRED"` and null provider.
  - Credential safety: Extracts variable names for each adapter with zero secret values.
  - Audit logging: Records `integration_adapter.planning.started`, `integration_adapter.planning.completed`, and `integration_adapter.planning.failed` events.
- **Execution Planning Service (`ExecutionPlanningService`)**:
  - Generates deterministic execution steps (`step-1`, `step-2`, ...).
  - `step-1`: `VALIDATE_CONFIGURATION` (root step, checks required environment variable names).
  - `step-2`: `VALIDATE_PREREQUISITES` (depends on `step-1`, verifies network readiness).
  - `step-3+`: Adapter operations mapped into execution steps with explicit `depends_on` chains.
  - Safety classification: Marks steps with safety levels (`CONFIGURATION`, `READ_ONLY`, `WRITE`, `DESTRUCTIVE`, `EXTERNAL_NETWORK`, `CREDENTIAL_REQUIRED`).
  - Approval boundary: Requires approval for non-READ_ONLY steps.
  - Strict non-execution boundary: All adapter operations marked `status = "BLOCKED"` with explicit blocked reason (`External execution is disabled in Control Plane. Phase 08 plans execution only.`).
  - Plan-level status set to `REQUIRES_APPROVAL`.
  - Audit logging: Records `execution_plan.started`, `execution_plan.completed`, and `execution_plan.failed` events.
- **API Endpoints**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/integration-adapters`: Generate adapters (201 Created).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/integration-adapters`: List adapters (200 OK).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/integration-adapters/{adapter_id}`: Retrieve adapter (200 OK).
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/execution-plans`: Generate execution plan (201 Created).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/execution-plans`: List execution plans (200 OK).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/repositories/{repository_id}/snapshots/{snapshot_id}/execution-plans/{plan_id}`: Retrieve execution plan (200 OK).
- **Test Fixtures**:
  - `backend/tests/fixtures/repositories/payments-storage-demo`: Stripe, PostgreSQL, AWS S3, Redis, `.env.example`.
  - `backend/tests/fixtures/repositories/webhook-demo`: Static webhook routes (`POST /webhooks/stripe`, `POST /callbacks/github`), `.env.example`.
  - `backend/tests/fixtures/repositories/adapter-unknown-demo`: Custom unclassified proprietary SDK.
- **Automated Test Suite**:
  - `backend/tests/test_integration_adapters.py`: 8 comprehensive tests covering lifecycle, payments/storage classification, webhook detection, unknown adapter review requirements, credential safety (zero secret values), determinism, tenant isolation anti-enumeration (404), and RBAC permissions.
  - `backend/tests/test_execution_plans.py`: 7 comprehensive tests covering lifecycle, step ordering and prerequisite DAG dependencies, safety classifications, approval and blocked boundaries, credential references without values, tenant isolation anti-enumeration (404), and RBAC permissions.
  - Full backend test suite: **81 / 81 passed** in 164.14s with zero regressions.
  - Ruff linter: **0 errors** (`All checks passed!`).
- **Frontend Studio UI & Client**:
  - Typed client in `frontend/src/lib/api.ts` with `integrationAdaptersApi`, `executionPlansApi`, and all domain types.
  - Phase 08: Integration Adapter Management Studio panel with planned adapters list, operation mapping tables, environment keys, and credential variable references.
  - Phase 08: Declarative Execution Planning Studio panel with deterministic step sequence, safety classification badges, approval badges, blocked boundary indicators, and explicit non-execution warning banner.
  - Strictly **NO execute button** anywhere in the interface.
  - Frontend Vitest unit tests: **1 / 1 passed**.
  - Frontend Next.js production build: Compiled cleanly with zero errors.

### Architectural & Technology Decisions
1. **Strict Non-Execution Invariant**: Phase 08 is exclusively an integration adapter modeling and execution planning layer. External operations are strictly marked `status = "BLOCKED"` with explicit blocked reasons. No external services are invoked, no subprocesses are spawned, and no repository code is executed.
2. **Zero Secrets Invariant**: Under no circumstance are secret values read from `.env` files or workspaces, saved to the database, or transmitted to the client. Only variable names (e.g. `DATABASE_URL`, `STRIPE_SECRET_KEY`) and safety metadata are cataloged.
3. **Deterministic Planning**: Step generation and dependency DAGs are 100% deterministic functions of the snapshot revision and candidate integrations. Identical inputs produce identical ordered adapters, operations, and execution steps. Zero LLM or AI tokens are consumed.
4. **Unknown Dependency Safety Boundary**: Any detected candidate or dependency that does not map to a recognized provider defaults to `AdapterType.UNKNOWN` with `status = "REVIEW_REQUIRED"` and requires explicit human review before integration.
5. **Anti-Enumeration Multi-Tenant Containment**: All adapter and execution plan endpoints strictly resolve the complete containment hierarchy (`User` → `Organization Membership` → `Project` → `Repository` → `RepositorySnapshot` → `Resource`). Cross-tenant access returns 404 Not Found rather than 403 Forbidden to eliminate resource ID enumeration.
6. **Strict Scope Boundary**: Zero Phase 09+ execution runtime, sandbox execution, agent harness, MCP generation, or tool registries were introduced.

### Deviations
None. All implementations conform to Design Phases 1–27 and the Phase 08 specification.

### Blockers
None.

---

## Phase B Log — MVP Realignment: Frontend Studio Restructuring & UX Architecture

### Objective
Restructure the Fussion Frontend Studio around the customer mental model (`PROJECT` → `WEBSITE` → `KNOWLEDGE` → `ASSISTANT` → `INTEGRATION` → `LIVE`) before implementing MVP Phase 09. Decompose the monolithic `frontend/src/app/page.tsx` into clean, modular, maintainable components while preserving the dark theme aesthetic and moving technical diagnostics (Phases 06–08) to a secondary view.

### Completed Work
- **Architectural Decomposition**:
  - Refactored monolithic 3,089-line `frontend/src/app/page.tsx` down to 488 lines (84% reduction), converting it into a clean page orchestrator managing state, API handlers, and modal lifecycles.
  - Established modular directory structure under `frontend/src/components/studio/` with dedicated `tabs/` and `modals/` subdirectories.
- **Header & Navigation Layer**:
  - `StudioHeader.tsx`: Renders product branding ("Fussion Studio / AI Integration Engineer"), project selection dropdown, "New Project" modal trigger, and operational health badge.
  - `StudioNavigation.tsx`: Distinct navigation bar separating primary customer journey tabs (`Overview`, `Website`, `Knowledge`, `Assistant`, `Integration`) from secondary system tabs (`Diagnostics`, `Settings`).
- **Customer Journey Tabs**:
  - `OverviewTab.tsx`: 6-stage customer journey progression stepper (`Project Setup`, `Website Connected`, `Knowledge Base`, `Assistant Design`, `Integration & PR`, `Live Assistant`), status summary cards, and quick navigation shortcuts.
  - `WebsiteTab.tsx`: Repository management, active snapshot card, source inspection metrics, and frontend framework/layout shell summary (`app/layout.tsx`, Tailwind CSS).
  - `KnowledgeTab.tsx`: Phase B UX shell for upcoming Phase 09 with document dropzone preview, format guidance (PDF, MD, TXT), and sample document grounding list.
  - `AssistantTab.tsx`: Phase B UX shell for upcoming Phase 10 with branding controls (name, greeting, color, starter prompt) and live interactive chat widget mockup.
  - `IntegrationTab.tsx`: Phase B UX shell for upcoming Phase 11/12 with a 4-stage delivery pipeline, proposed `app/layout.tsx` mock diff review, and sandbox verification stages.
- **Secondary Diagnostics & System Tabs**:
  - `DiagnosticsTab.tsx`: Dedicated home for Phase 06–08 deep engineering tools (Architecture Discovery, OpenAPI 4-bucket reconciliation, cloud integration planning, declarative adapters, and blocked execution DAGs) with strict non-execution banners and zero execute triggers.
  - `SettingsTab.tsx`: Backend operational telemetry, PostgreSQL database latency/status, project configuration metadata, and multi-tenant containment security invariants.
- **Extracted Studio Modals**:
  - `NewProjectModal.tsx`: Project creation modal.
  - `NewIntegrationModal.tsx`: Provider integration connection modal.
  - `NewRepoModal.tsx`: Source repository registration modal.
  - `AcquireSnapshotModal.tsx`: Revision/branch checkout modal.
- **Testing & Verification**:
  - `frontend/src/__tests__/page.test.tsx`: Updated to assert new Studio branding and operational health status.
  - `frontend/src/__tests__/studio.test.tsx`: Created comprehensive unit test suite covering StudioHeader, StudioNavigation, and all 7 individual tabs.
  - Vitest suite: **10 / 10 passed** across 2 test files.
  - Next.js Turbopack build: Compiled cleanly with **zero TypeScript errors** (`next build` exit code 0).
  - Backend regression suite: **81 / 81 passed** in `backend/tests/` with zero regressions.

### Architectural & Technology Decisions
1. **Customer-Centric Mental Model**: The frontend is organized strictly around the customer journey to add an AI assistant to their website, moving away from low-level cloud integration DAGs.
2. **Progressive Disclosure**: Deep engineering diagnostics (AST discovery, OpenAPI reconciliation, adapters) are preserved intact under the dedicated `Diagnostics` tab for developer visibility without cluttering the primary user journey.
3. **Strict Phase B Boundary**: Zero backend models, PDF parsers, vector embeddings, LLM calls, sandbox runners, or PR creation mechanisms were introduced. All Phase 09-12 views are strictly UX shells.
4. **Preserved Visual Identity**: Preserved existing dark theme, typography, cards, badges, and layout aesthetics.

### Deviations
None. All implementations conform to the Phase B specification.

### Blockers
None.

---

## Phase B.1 Log — MVP Realignment: Frontend Authentication & Application Architecture Foundation

### Objective
Integrate the existing Fussion backend authentication system into the frontend, establish a clean, scalable, modern Next.js frontend architecture with route groups `(auth)` and `(app)`, protect `/studio`, decompose the monolithic API client into domain-based services (`lib/api/`), and preserve all Phase B Studio functionality without regressions.

### Completed Work
- **API Client Decomposition (`frontend/src/lib/api/`)**:
  - `client.ts`: Core HTTP client with `NEXT_PUBLIC_API_URL`, dynamic token storage (`localStorage` fallback to memory), `ApiClientError` hierarchy, automatic Bearer auth injection, and 401 response handling.
  - `auth.ts`: Authentication endpoints (`login`, `register`, `getMe`) and typed contracts (`User`, `LoginRequest`, `RegisterRequest`, `TokenResponse`).
  - Domain API modules: `health.ts`, `projects.ts`, `integrations.ts`, `repositories.ts`, `snapshots.ts`, `discovery.ts`, `contracts.ts`, `integration-plans.ts`, `adapters.ts`, `execution-plans.ts`.
  - `index.ts`: Central export module for all domain API functions and interfaces.
  - Backwards-compatibility layer: Preserved `frontend/src/lib/api.ts` re-exporting `lib/api/index`, preventing any breakage in existing components and tests.
- **Authentication Feature Layer (`frontend/src/features/auth/`)**:
  - `types.ts`: Auth state interfaces (`AuthState`, `AuthContextType`, `LoginCredentials`, `SignupCredentials`).
  - `context.tsx`: `AuthProvider` context managing auth state (`isAuthenticated`, `isLoading`, `user`, `token`), initial session hydration via `GET /api/v1/auth/me`, token storage, and `login`, `signup`, and `logout` actions.
  - `components/LoginForm.tsx`: Professional developer-focused login form with client validation, error banners, loading indicators, and link to sign up.
  - `components/SignupForm.tsx`: Registration form with full name, email, organization name, password confirmation, validation rules, error banners, and link to login.
  - `components/ProtectedRoute.tsx`: Route guard wrapper rendering an animated Fussion loading skeleton during authentication checks, redirecting unauthenticated users to `/login`.
  - `index.ts`: Feature-level export barrel.
- **App Router Restructuring (`frontend/src/app/`)**:
  - Root Layout (`layout.tsx`): Wrapped application in `<AuthProvider>` with enhanced SaaS metadata and dark aesthetic.
  - Root Page (`page.tsx`): Intelligent root router redirecting authenticated users to `/studio` and unauthenticated users to `/login`.
  - Auth Route Group `(auth)`:
    - `layout.tsx`: Centered dark container with ambient glow and security badge.
    - `login/page.tsx`: Sign-in page with automatic redirection to `/studio` if already authenticated.
    - `signup/page.tsx`: Registration page with automatic redirection to `/studio` if already authenticated.
  - App Route Group `(app)`:
    - `layout.tsx`: Protected application shell wrapping children in `<ProtectedRoute>`.
    - `studio/page.tsx`: Studio Orchestrator migrated cleanly from Phase B, integrated with `useAuth()` to display user profile and handle sign-out.
- **Studio Header Integration (`frontend/src/components/studio/StudioHeader.tsx`)**:
  - Added user identity indicator (`user.full_name || user.email`) and interactive "Sign Out" button triggering `auth.logout()`.
- **Testing & Verification**:
  - `frontend/vitest.setup.ts`: Configured comprehensive `next/navigation` router mocks (`useRouter`, `usePathname`, `useSearchParams`, `redirect`).
  - `frontend/src/__tests__/auth.test.tsx`: 16 tests covering `LoginForm`, `SignupForm`, `AuthProvider`, `ProtectedRoute`, and root page redirection.
  - `frontend/src/__tests__/studio.test.tsx`: 11 tests verifying StudioHeader user profile, logout trigger, navigation, and all 7 studio tabs.
  - `frontend/src/__tests__/page.test.tsx`: 1 test verifying Studio page orchestration inside auth provider.
  - Frontend Vitest: **28 / 28 passed** across 3 test files.
  - Next.js Turbopack build: **Compiled cleanly with exit code 0 and 0 TypeScript errors**, generating routes `/`, `/_not-found`, `/login`, `/signup`, and `/studio`.

### Architectural & Technology Decisions
1. **Next.js App Router Route Groups**: Utilized `(auth)` and `(app)` route groups to cleanly isolate unauthenticated layouts (centered auth card) from protected application layouts without affecting URL structure (`/login`, `/signup`, `/studio`).
2. **Domain-Driven API Client Decomposition**: Split the monolithic 260-line API client into dedicated domain modules under `frontend/src/lib/api/` while providing a backwards-compatible `frontend/src/lib/api.ts` facade to guarantee zero regressions.
3. **No External State Libraries**: Auth state is managed purely via React Context (`AuthProvider`) with persistent `localStorage` token storage, honoring the project guideline to avoid redundant state management libraries (no Redux, Zustand, React Query).
4. **Instant Registration Experience**: Backend `POST /api/v1/auth/register` automatically returns a valid JWT token and creates the default organization; the frontend immediately hydrates the user session and navigates directly to `/studio`.
5. **Strict Scope Boundary**: Zero Phase 09 (Knowledge Base / RAG / embeddings), Phase 10 (Assistant / Widget generation), Phase 11 (Sandbox / PR creation), or Phase 12 (Visitor chat runtime) functionality was introduced.

### Deviations
None. All implementations conform to the Phase B.1 specification.

### Blockers
None.

---

## Phase 09 Log — Knowledge Base Foundation

### Objective
Establish the project-scoped Knowledge Base foundation that will ground customer website AI assistants. Implement safe multi-format document extraction (PDF, Markdown, Plain Text), deterministic character/word chunking, deterministic 384-dimensional normalized vector embeddings (zero token cost, zero LLM dependencies), database persistence with cascade deletion, semantic retrieval ranking with citation locations, and an authenticated Studio Knowledge Base interface replacing the Phase B preview placeholder.

### Completed Work
- **Dependencies**:
  - Added `pypdf>=5.0.0` and `python-multipart>=0.0.12` to `backend/pyproject.toml`.
  - Synchronized environment using `uv sync --extra dev`.
- **Database Architecture & Models (`backend/app/models/knowledge.py`, `project.py`)**:
  - `DocumentStatus`: Enum (`PENDING`, `PROCESSING`, `READY`, `FAILED`).
  - `KnowledgeBase`: 1-to-1 relationship with `Project` (`projects 1 ── 1 knowledge_bases`, unique FK `project_id`, cascading delete).
  - `KnowledgeDocument`: Belongs to `KnowledgeBase` (`knowledge_bases 1 ── N knowledge_documents`), tracks filename, content_type, size, status, error_message, chunks_count, and raw_text.
  - `KnowledgeChunk`: Belongs to `KnowledgeDocument` (`knowledge_documents 1 ── N knowledge_chunks`), stores `chunk_index`, `text`, `page_number`, `source_location`, `token_count`, `embedding` (384-dim normalized floats stored as JSON), and `embedding_model`.
  - Exported through `app.models.__init__.py` and updated `Project.knowledge_base`.
- **Database Migrations (`backend/alembic/versions/0009_knowledge_base.py`)**:
  - Migration `0009_knowledge_base` with down revision `0008_integration_adapters`.
  - Created `document_status` enum, `knowledge_bases`, `knowledge_documents`, and `knowledge_chunks` tables with indexes and cascade constraints.
  - Verified full migration cycle: `alembic upgrade head -> downgrade -1 -> upgrade head` passed cleanly.
- **RBAC & Authorization Matrix (`backend/app/core/permissions.py`, `backend/app/api/deps.py`)**:
  - Added `knowledge:view`, `knowledge:create`, `knowledge:delete`.
  - Assigned permissions: OWNER, ADMIN, MEMBER have view/create/delete; VIEWER has view only.
  - Scoped dependencies: `get_or_create_knowledge_base` and `get_current_knowledge_document` enforce strict multi-tenant and project containment.
  - Cross-tenant / cross-project access returns **HTTP 404 Not Found** to prevent resource enumeration.
- **Deterministic Embeddings Service (`backend/app/services/knowledge/embeddings.py`)**:
  - `EmbeddingProvider` abstract interface.
  - `DeterministicHashEmbeddingProvider`: Multi-resolution feature hashing over word tokens, character trigrams, and character 4-grams projected into 384 dimensions.
  - L2 normalized vectors ($\|v\|_2 = 1.0$). Exact cosine similarity via dot product.
  - Zero external network requests, zero API keys, zero LLM calls, zero token cost. Identical text produces identical vectors.
- **Text Extraction & Deterministic Chunking (`backend/app/services/knowledge/chunking.py`)**:
  - Safe PDF extraction via `pypdf.PdfReader` retaining page numbers (`Page N`).
  - Markdown extraction recognizing headings (`#`, `##`, `###`) and retaining heading contexts (`Heading: ...`).
  - Plain text paragraph and sentence boundary preservation.
  - Target: ~500 characters with ~100 characters overlap without breaking words.
  - Sequential deterministic chunk indexes (0, 1, 2...).
- **Ingestion Pipeline (`backend/app/services/knowledge/ingestion.py`)**:
  - Enforced 10 MB maximum file size limit.
  - Strictly allowed formats: PDF (`application/pdf`), Markdown (`text/markdown`), Plain Text (`text/plain`).
  - Validation: rejects unsupported extensions (.exe, .jpg, etc.), MIME mismatches, invalid PDF headers (missing `%PDF-`), and invalid UTF-8 text.
  - Pipeline: `Validate` → `Persist Document (PROCESSING)` → `Extract text` → `Chunk` → `Embed` → `Persist chunks` → `READY`.
  - Safe error handling: on failure, rolls back chunks, marks document `FAILED`, and stores sanitized error message.
  - Audit logging: emits `knowledge.document.uploaded`, `knowledge.document.processed`, and `knowledge.document.failed` events.
- **Semantic Retrieval Service (`backend/app/services/knowledge/retrieval.py`)**:
  - `query_knowledge_base`: Embeds query string, calculates cosine similarity against all READY chunks in the target project's knowledge base, filters by `score_threshold`, sorts descending by score, and returns top $K$ results with source filename and citation locations.
  - Embeddings are strictly internal and never exposed in the public API.
- **REST Endpoints (`backend/app/api/v1/endpoints/knowledge.py`, `router.py`)**:
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents`: Multipart upload (`KNOWLEDGE_CREATE`).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents`: List documents (`KNOWLEDGE_VIEW`).
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents/{document_id}`: Document details & chunks (`KNOWLEDGE_VIEW`).
  - `DELETE /api/v1/organizations/{org_id}/projects/{project_id}/knowledge/documents/{document_id}`: Delete document & cascade chunks (`KNOWLEDGE_DELETE`).
  - `POST /api/v1/organizations/{org_id}/projects/{project_id}/knowledge/query`: Semantic retrieval test (`KNOWLEDGE_VIEW`).
- **Frontend Domain API Client (`frontend/src/lib/api/knowledge.ts`)**:
  - Updated `client.ts` to support `FormData` without overriding multipart boundary headers.
  - Typed `knowledgeApi` methods: `listDocuments`, `getDocument`, `uploadDocument`, `deleteDocument`, `queryKnowledge`.
  - Re-exported via `frontend/src/lib/api/index.ts` and `frontend/src/lib/api.ts`.
- **Frontend Knowledge Feature Layer (`frontend/src/features/knowledge/`)**:
  - `types.ts`: Domain models and component interfaces.
  - `useKnowledgeBase.ts`: Custom hook managing document loading, file upload, deletion, citation inspection, and semantic query testing.
  - `DocumentUpload.tsx`: Drag-and-drop dropzone with format/size checks and progress feedback.
  - `DocumentStatusBadge.tsx`: Status badges for PENDING, PROCESSING, READY, and FAILED.
  - `DocumentList.tsx`: Tabular document listing with file format badges, size, chunk count, upload date, Inspect action, and Delete action.
  - `ChunkPreview.tsx`: Individual chunk card with index, page/heading citation badge, word count estimate, and formatted text excerpt.
  - `DocumentDetails.tsx`: Modal viewing document metadata, failure errors, and all extracted chunk previews with citations.
  - `KnowledgeQuery.tsx`: Grounding retrieval tester with tuning sliders (top-k, score threshold) and ranked citation result cards.
  - `KnowledgeBaseView.tsx`: Top-level feature orchestrator.
- **Studio Integration (`frontend/src/components/studio/tabs/KnowledgeTab.tsx`)**:
  - Replaced Phase B preview placeholder with real `<KnowledgeBaseView orgId={orgId} projectId={projectId} />`.
  - Connected Studio project state to `KnowledgeTab`.
- **Verification & Automated Tests**:
  - `backend/tests/test_knowledge.py`: 14 comprehensive tests covering security/tenant isolation (404), RBAC enforcement (viewer 403, owner 201), upload validation (PDF, MD, TXT, invalid MIME, 10MB limit), processing states, chunking determinism, embedding properties, retrieval ranking, and cascade deletion.
  - Full backend test suite: **95 / 95 passed** in 165s with zero regressions.
  - Ruff linter: **0 errors** (`All checks passed!`).
  - Frontend test suite (`knowledge.test.tsx`, `studio.test.tsx`, `auth.test.tsx`, `page.test.tsx`): **41 / 41 passed**.
  - Frontend Next.js Turbopack build: **Exit code 0, 0 TypeScript errors**.

### Architectural & Technology Decisions
1. **Local Deterministic Embeddings**: Built a 384-dimensional feature hashing embedding provider to ensure zero external API dependencies, zero LLM dependencies, and zero cost during development and CI testing, while establishing the exact embedding interface required for grounding.
2. **Citation-First Chunking**: Extraction preserves physical page numbers for PDFs (`Page N`) and semantic headings for Markdown (`Heading: ...`), enabling grounding results to cite precise source locations.
3. **Strict Multi-Tenant Containment**: Every knowledge resource is accessed via `Organization` → `Project` → `KnowledgeBase` → `Document` → `Chunk`. Cross-tenant and cross-project requests return 404 to prevent resource discovery.
4. **Non-Execution Security**: Uploaded files are strictly treated as untrusted data. Zero shell commands, zero dynamic code evaluation, and zero executable rendering are permitted.
5. **Clean Phase Boundary**: Strictly zero LLM chat, assistant runtime, widget generation, MCP registries, or PR creation were implemented.

### Deviations
None. All implementations conform to the Phase 09 specification.

### Blockers
None.

---

## Phase 10 Log

### Objective
Implement Phase 10 — Assistant Configuration & Widget Generation. Establish the project-scoped assistant configuration and interactive live widget preview layer between Phase 09 (Knowledge Base) and Phase 11 (Website Integration & GitHub PR Pipeline).

### Completed Work
- **Database Model & Relationships (`backend/app/models/assistant.py`, `project.py`, `__init__.py`)**:
  - `AssistantPosition`: Enum with `BOTTOM_RIGHT` and `BOTTOM_LEFT`.
  - `Assistant`: Model with UUID PK, 1-to-1 project relationship (`ondelete="CASCADE"`, unique, indexed), identity parameters (`name`, `description`, `welcome_message`, `starter_prompt`), appearance styling (`brand_color`, `text_color`, `position`, `avatar_url`), behavior controls (`is_enabled`, `system_instructions`), and UTC timestamps.
  - Linked `Project.assistant` relationship (`uselist=False, cascade="all, delete-orphan"`).
  - Exported in `backend/app/models/__init__.py`.
- **Alembic Migration (`backend/alembic/versions/0010_assistant.py`)**:
  - Created migration with `down_revision = "0009_knowledge_base"`.
  - Reversible cycle verified: `alembic upgrade head` -> `alembic downgrade -1` -> `alembic upgrade head`.
- **RBAC & Scoping (`backend/app/core/permissions.py`, `backend/app/api/deps.py`)**:
  - Added permissions: `assistant:view`, `assistant:create`, `assistant:update`, `assistant:delete`.
  - Configured role permission matrix: `OWNER`, `ADMIN`, `MEMBER` have full view/create/update/delete; `VIEWER` has view-only.
  - Implemented `get_or_create_assistant` and `get_current_assistant` dependencies strictly scoped via `Organization` → `Project` hierarchy with 404 anti-enumeration isolation.
- **Pydantic Schemas (`backend/app/schemas/assistant.py`)**:
  - `AssistantRead`: Complete declarative configuration model (`from_attributes=True`).
  - `AssistantCreate` and `AssistantUpdate`: Validated inputs with length bounds.
  - `AssistantPreview`: Combined preview payload including assistant config, Knowledge Base grounding status (`has_knowledge_base`, `documents_count`, `ready_chunks_count`), and mock sample messages.
  - Re-exported in `backend/app/schemas/__init__.py`.
- **Validation & Service Layer (`backend/app/services/assistant/`)**:
  - `validation.py`: Strict hex color regex (`^#[0-9A-Fa-f]{6}$`), secure URL scheme check (http/https only, max 500 chars), and string length constraints.
  - `configuration.py`: Default initialization, configuration updates with audit events (`assistant.configuration.updated`), reset to defaults (`assistant.configuration.reset`), and preview payload generator.
- **REST Endpoints & Router (`backend/app/api/v1/endpoints/assistant.py`, `router.py`)**:
  - `GET /api/v1/organizations/{org_id}/projects/{project_id}/assistant`: Auto-creates default configuration if missing (`ASSISTANT_VIEW`).
  - `PUT /` & `PATCH /`: Updates assistant configuration with validation (`ASSISTANT_UPDATE`).
  - `DELETE /` & `POST /reset`: Resets configuration to canonical Fussion defaults (`ASSISTANT_DELETE`).
  - `GET /preview`: Returns widget preview configuration payload with knowledge base connection stats (`ASSISTANT_VIEW`).
  - Mounted in `api_v1_router`.
- **Frontend API Client (`frontend/src/lib/api/assistant.ts`)**:
  - Typed methods: `getAssistant`, `updateAssistant`, `resetAssistant`, `getAssistantPreview`.
  - Re-exported in `frontend/src/lib/api/index.ts` and compatibility facade `frontend/src/lib/api.ts`.
- **Frontend Feature Layer (`frontend/src/features/assistant/`)**:
  - `types.ts`: Domain form and preview state interfaces.
  - `useAssistant.ts`: Hook managing server state, deep draft vs baseline dirty tracking, save, discard, and reset actions.
  - `AssistantIdentityForm.tsx`: Name, description, welcome greeting, and starter prompt controls.
  - `AssistantAppearanceForm.tsx`: Preset color palettes, native color pickers, position selectors (`Bottom Right` vs `Bottom Left`), and avatar URL input with image preview fallback.
  - `AssistantBehaviorForm.tsx`: Active state toggle switch and declarative system instructions.
  - `AssistantSaveBar.tsx`: Floating action bar appearing strictly on dirty state with Discard, Reset Defaults, and Save Changes buttons.
  - `AssistantPreview.tsx`: Live reactive mock widget with desktop/mobile viewport switcher, expandable chat popup, starter prompt interaction, and Knowledge Base grounding badge.
  - `AssistantStatus.tsx`: Summary badge card showing ID, Active status, Position, and KB connection stats.
  - `AssistantView.tsx`: Top-level two-column layout assembling settings and live sticky preview.
- **Studio Tab Integration (`frontend/src/components/studio/tabs/AssistantTab.tsx`, `studio/page.tsx`)**:
  - Mounted `<AssistantView orgId={orgId} projectId={projectId} />` in `AssistantTab`.
  - Passed `orgId` and `projectId` from selected project in Studio page.
- **Verification & Automated Tests**:
  - Backend: `backend/tests/test_assistant.py` (13 tests) passing; full suite **108 / 108 passed** with zero regressions.
  - Ruff linter: **0 errors** (`All checks passed!`).
  - Frontend: `frontend/src/__tests__/assistant.test.tsx` (12 tests) passing; full suite **53 / 53 passed** across 5 test files.
  - Next.js Turbopack build: **Exit code 0, 0 TypeScript errors**.

### Architectural & Technology Decisions
1. **Zero LLM / Local Simulation**: Phase 10 preview is purely client-side UI simulation with deterministic mock responses communicating styling and Knowledge Base connection state without invoking any AI APIs or incurring token costs.
2. **Auto-Initialization**: Projects automatically initialize a default assistant configuration on first read, ensuring users never encounter an unconfigured or empty state.
3. **Deep Dirty Tracking**: The Save Bar only appears when actual draft fields differ from the persisted baseline, allowing clean discard and preventing accidental dirty state triggers on pure focus/blur.
4. **Anti-Enumeration 404 Scoping**: Cross-tenant or cross-project access attempts return HTTP 404, preventing resource enumeration across tenants.
5. **Strict Phase Boundary**: Zero PR generation, sandbox execution, visitor runtime, or iframe injection were implemented.

### Deviations
None. All implementations conform to the Phase 10 specification.

### Blockers
None.

---

### Next Phase
*(Historical note: this section recorded the next legacy phase. Phase numbering was retired on
2026-09-12 — what comes next is now the Step status table at the top of this file.)*

---

## Phase 11 Log — Remediation: customer-file overwrite (CLAUDE.md §3.1)

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0: writes to a customer repository), declared
at the start and unchanged throughout.

**Status: COMPLETED** — fussion-reviewer round 2 PASS WITH FINDINGS; committed as `415d5e3` and
merged to `main` on 2026-09-12 (fast-forward). Phase 11 code was already running (the table above
still says PENDING; reconciling the table and the two roadmaps is its own step-A slice, and is
the next one). Baseline commit `f4027e0`.

### Objective
FEASIBILITY.md step A, one slice: stop the integration pipeline replacing or corrupting
the customer's widget target (`app/layout.tsx` / `index.html`).

### Completed Work
- **Read at a pinned commit, branch from the same commit.** New Protocol methods
  `get_file_contents(owner, repo, path, ref)` and `get_branch_head(owner, repo, branch)`;
  `create_branch` takes `base_sha`. The pipeline resolves the default branch's head once,
  reads the target at that SHA, records it as `plan_summary.base_sha`, and branches from it,
  so a customer commit landing mid-run is never silently reverted (it merges cleanly if it
  does not overlap Fussion's change, and conflicts if it does).
- **Missing target is refused**, not created: `IntegrationRefusedError` → HTTP 422
  "Integration refused: …", audit event `integration.run.refused`, before any branch or
  commit exists. (Creating a root `app/layout.tsx` in a `src/app` repo hijacks Next.js
  routing.) The full FR-100 failure taxonomy stays deferred to step D.
- **Validator — only Fussion-managed blocks may change.** Every file in `files_to_modify`
  must have its original supplied; outside managed blocks, the original and generated
  files must be identical after removing whitespace. Insertions, deletions and in-line
  rewrites are rejected with a line number (never customer source). Known limits: an edit
  wrapped in Fussion marker text bypasses the check (a gate on wiring `GitHubProvider` in,
  below), and whitespace changes are not detected even where they change meaning
  (`return (` → `return\n(` renders a blank page; `"admin hidden"` → `"adminhidden"` drops
  a class).
- **No stub fallback.** `generate_artifacts` requires `widget_target_path` and
  `existing_target_content`; both hardcoded stubs are deleted. `get_run_diff` now raises
  (CLAUDE.md §3.7), deliberately.
- **Line endings.** Patched targets keep the original's dominant line ending; the sandbox
  writes and reads with `newline=""` (no `\r\r\n` on Windows).
- **GitHub error classification.** `GitHubUnavailableError` (subclass of `GitHubAPIError`)
  for network failures, 429, rate-limit 403s, 5xx and unreadable responses; 401/other 403s,
  directories, >1 MB, non-UTF-8 and invalid paths stay `GitHubAPIError`. Unsafe paths
  (`..`, leading `/`, `\`, empty segments) are rejected before any request.
- **`GET /plan`** reads the target and reports `target_status` (`exists` / `missing` /
  `unknown`); only `GitHubUnavailableError` degrades to `unknown`, anything else is a 400
  naming the cause. The planner declares exactly the path that is read (no defaulting).
- **Tests.** Red first, twice. Round 1: the preservation pipeline test failed on the
  unfixed pipeline (committed layout was the stub). Round 2: in-line rewrite, attribute
  injection and outside-block insertion were accepted by the round-1 validator, and the
  race test showed the integration commit parented on the customer's mid-run commit; all
  pass now. Provider-contract tests run against both `GitHubProvider`
  (`httpx.MockTransport`) and the mock. Fixture:
  `backend/tests/fixtures/repositories/nextjs-distinctive-layout/`.

### Architectural & Technology Decisions
1. Only-managed-blocks-change, not "recognisable fragment" or "characters in order": the
   stub shares `return (`, `</html>`, `);`, `}` with real layouts, and an in-order check
   accepts `isAdmin` → `!isAdmin` (MVP-REQUIREMENTS-V2 Part C #6).
2. The widget target is always a modification, never a create; `target_status` is a
   required keyword on `IntegrationPlanner.generate_plan`.
3. New types, each for a named need: `GitHubUnavailableError` (transient vs configuration
   failure, decision 3), `IntegrationRefusedError` (refused vs crashed, FR-100 subset).
   `GitHubProvider` gained an optional `transport` for tests only.

### Review history
- Round 1 — **BLOCKED**: read-then-branch race (§4.8); in-order validator accepted
  in-line rewrites; stub fallback still reachable; preview hid configuration errors as
  "unreachable"; docs overclaimed. All addressed in round 2.
- Round 2 (fresh reviewer, no round-1 context) — **PASS WITH FINDINGS**. All five round-1
  findings independently verified resolved; no BLOCKING finding. New findings: marker
  text bypasses the validator; `/plan` misreports repo/branch/token 404s as "missing"; docs
  omitted that every Studio run now fails closed; plus considers (whitespace can change
  meaning, "PR conflict" overclaimed, `base_sha` default, mixed line endings normalised,
  every `</body>` patched). FR-096 and FR-097 flagged as unmet and unlogged. Under §9.0's
  stopping rule none is reachable by the code as it runs, so all were logged — docs only,
  no code change after the review, so the reviewed diff is the committed diff.

### Deviations
Checked against the approved plan and the original prompt:
- The prompt's "fragment" rule and "missing target = create" were both replaced (approved).
- Round 2 widened the slice to close every round-1 finding (approved): `create_branch`
  signature, `get_branch_head`, error classification, sandbox `newline=""`, planner no
  longer defaults an empty path, `get_run_diff` left broken.
- Baseline commit also fixed `.gitignore`: the Python `lib/` rule was silently excluding
  `frontend/src/lib/`; `data/` and `backend/data/` (~25k workspace files) now ignored.
- Installed `.claude/agents/fussion-reviewer.md` and `.claude/commands/done.md`.
- CLAUDE.md §8 gained a test-database caveat (not requested; kept by owner).
- Round-2 findings were logged, not fixed (owner chose docs-only, so the reviewed diff is
  the committed diff); the `base_sha` default in particular stays for the next slice.

### Blockers / Deferred
- **Every Studio integration run now ends in HTTP 422 "Integration refused" — intended.**
  The running app uses the file-less `MockGitProvider`, so the target is never found and
  the pipeline fails closed instead of writing a file it has not read. This is not a bug;
  restoring a stub or default layout would reintroduce §3.1. CLAUDE.md §2.
- **Blockers on wiring `GitHubProvider` in** — the gate; canonical list in CLAUDE.md §3.
  Nothing goes near a real repository until it is empty. Logged under §9.0's stopping rule
  (not reachable by the code as it runs):
  - FR-096 protected paths not enforced (`.github/workflows/deploy.yml` passes validation)
    — violates CLAUDE.md invariant §4.9, added after this slice's review
  - marker-pair discipline (framework match, pair count, own-line) — required before the
    step-D CodingAgent
  - `/plan` reports private-repo, wrong-branch and bad-token 404s as "file missing"
  - `create_branch`'s `base_sha=None` default lets a future caller reintroduce the race
  - FR-097 generated-code security scan does not exist
- **Hard blocker on first push:** the baseline commit `f4027e0` put the real dev
  `SECRET_DEV_ENCRYPTION_KEY` (and `JWT_DEV_SECRET`) into git history. Before adding a
  remote: rewrite history, or treat both as compromised and rotate. CLAUDE.md §3.2.
- **`GET /runs/{id}/diff` raises** until the change set is persisted — CLAUDE.md §3.7.
- PR body still claims "Sandbox validation: PASSED".
- Pre-existing patcher behaviour: every `</body>` is patched (including one inside a string
  literal), and a mixed-line-ending file is normalised to its dominant ending, rewriting
  every minority-ending line in the PR.
- `GENERIC_HTML` with a non-`.html` target always fails validation (pre-existing; fails closed).
- **Test environment (logged, not fixed):**
  - conftest should force the test DB URL regardless of `backend/.env`, and set
    `WindowsSelectorEventLoopPolicy` for psycopg async on Windows. Until then the suite
    only runs from the repository root.
  - The suite is not reproducible from a fresh clone: the fixture
    `backend/tests/fixtures/repositories/fastapi-nextjs-demo/.env` is gitignored, and
    fixture/workspace paths depend on the working directory (a clean checkout of `f4027e0`
    had 39 failures). Needs `!backend/tests/fixtures/**/.env` and cwd-independent paths.
    CI would fail today.
  - `test_adapter_unknown_classification` (Phases 05–08) failed once under load and
    passes in isolation and in clean runs — flaky; that subsystem may be deleted.

### Verification (2026-09-11, round 2)
- Ruff: `All checks passed!`
- Backend, run from the repository root: **172 passed** (121 pre-existing + 51 new).
- Frontend (untouched): `pnpm test` 108/108 passed (9 files); `pnpm build` exit 0.
- Evals: none exist yet.

---

## Step B (FEASIBILITY §3) · Slice B1 — public key + allowed origins

**Naming collision, deliberately spelled out:** this is slice **B1** of *step B* in
`docs/FEASIBILITY.md` §3, per `docs/implementation/STEP-B-SLICES.md`. It is **not** "Phase B.1"
in the table above, which is the completed frontend-authentication work. Nothing is added to that
table: it uses the phase numbering that `CLAUDE.md` §3.4 says must not be cited until the two
roadmaps are reconciled. Resolving this collision belongs to the roadmap-reconciliation slice.

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared before work started and unchanged. The
slice changes control-plane behaviour with no customer-repo, credential or cross-tenant path, and
nothing resolves tenancy from these fields until B2.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; committed as
`f8cc086` and merged to `main` on 2026-09-12, along with `fix/layout-overwrite` (the §3.1 fix),
which had been sitting unmerged. Both were fast-forwards; both branches are deleted. `main` had
been stuck at Phase 01 while two branches stacked on top of it. From now on a slice merges to
`main` as soon as the reviewer passes and the owner approves — `docs/DEVELOPMENT-WORKFLOW.md`
§2.5.

### Objective
FR-107: each website integration has a public client key and a set of registered allowed origins.
Store and manage both. **No behaviour:** nothing reads the key or checks an origin until the
tenant resolver in B2.

### Completed Work
- **Public key.** `website_integrations.public_key`, unique and indexed, generated server-side as
  `fussion_pk_` + `secrets.token_urlsafe(24)` (192 bits, so an unknown key cannot be enumerated).
  It is not a secret — it ships in the customer's page — so it is stored in plaintext for an
  indexed lookup in B2, and exposed read-only on `WebsiteIntegrationRead`. No create or update
  schema accepts it; tested.
- **`AllowedOrigin`** (`app/models/allowed_origin.py`): one row per registered origin, unique per
  `(integration_id, origin)`, ORM cascade from the integration (SQLite runs without
  `PRAGMA foreign_keys`, so the ORM relationship is what actually deletes them). Capped at 20 per
  integration. The same origin may be registered under two integrations: tenancy comes from the
  key, and the origin only validates it.
- **`app/core/origins.py` — `normalize_origin`.** One canonical form, `scheme://host[:port]`, so
  a stored origin and a browser's `Origin` header meet as exact strings. B2's resolver must use
  this same function. Rejects paths, queries, fragments, userinfo, wildcards, `null`, non-http(s)
  schemes, missing hosts and bad ports; requires https except for loopback hosts.
- **Endpoints** `GET/POST/DELETE .../website-integrations/origins`, scoped through the existing
  dependency chain, so every cross-tenant and cross-project id returns 404, not 403.
- **Migration 0012**: nullable add → per-row backfill → NOT NULL + unique index, then the
  `allowed_origins` table. The backfill reads each `id` and binds it straight back with no type
  coercion, so it does not depend on how a dialect renders a UUID.
- **Tests** (`tests/test_allowed_origins.py`, 51): written red-first — 45 failed and 1 passed
  before the code existed. The one that passed,
  `test_origins_require_an_integration`, passed vacuously (no route yet → 404) and is meaningful
  only now; it is kept because it pins the missing-integration case.

### Architectural & Technology Decisions
1. `normalize_origin` lives in `app/core/`, not `app/services/integration/`: that package's
   `__init__` imports the pipeline, which imports the schemas, so a schema importing from it is a
   circular import. `app/core/` is also the honest home for something the control plane and the
   future `app/runtime/` resolver both use.
2. `idna.encode(uts46=True, transitional=False)` rather than the stdlib `"idna"` codec — see
   review finding 1 below. `idna` is now a declared dependency; it was previously present only
   transitively through `httpx`, which is a **dev** dependency.
3. Audit recording moved to `app/services/audit.py` as a public `record_audit`. Three other
   modules still hold private `_record_audit` copies; consolidating all four is its own change.
4. No key rotation, no wildcard subdomains, no per-origin enable/disable (YAGNI). See Deferred.

### Review history
One round (Tier 2 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. Tier 2
confirmed; no finding showed Tier 1 reach. Findings 1–5 were defects in what this slice built, so
per §9.0 they were fixed in-slice and re-verified:
1. **IDNA mismatch (the significant one).** The stdlib codec is IDNA2003 and maps ß→ss, so
   `https://faß.example` was stored as `https://fass.example` — an origin the real site never
   sends, and one an unrelated `fass.example` would have matched once B2 compares headers. Now
   UTS-46 non-transitional, matching browsers. Regression tests added for all three hosts.
2. **Length checked before punycode expansion**, so a 228-character input could produce a
   270-character value for a `String(255)` column. Invisible on SQLite (VARCHAR unenforced) and a
   500 on Postgres (`DataError`, not `IntegrityError`). The check now runs on the canonical value;
   a test case covers it.
3. `String(255)` duplicated `MAX_ORIGIN_LENGTH` across a module boundary — the mechanism that hid
   finding 2. The model now imports the constant.
4. `allowed_origins.py` imported the private `_record_audit` from `website_integrations.py`;
   renaming it would have broken API start-up. Fixed by decision 3 above.
5. The "origin removed" audit event was written after the delete committed. It now records first,
   matching `delete_website_integration`.

Also fixed, from CONSIDER, because it concerns a credential in a response body: the 422 handler
rendered each error's `input`, so an over-length `github_token` was echoed back. `input` is now
stripped, with a test. (The handler needed touching regardless: it json-dumped `exc.errors()`
raw, which crashes on any `field_validator` ValueError — B1 added the app's first one.)

### Deviations
Checked against the approved plan, item by item:
- **Module moved.** The plan put `normalize_origin` in `app/services/integration/origins.py`; it
  is in `app/core/origins.py` (decision 1). Found while running the tests, not by inspection.
- **Two files the plan did not name** were changed: `app/core/errors.py` (the 422 handler, which
  B1's first `field_validator` made reachable) and `pyproject.toml`/`uv.lock` (the `idna`
  dependency). `app/services/audit.py` is new, and `website_integrations.py` changed by more than
  the planned one line, both from review finding 4.
- **Rotation endpoint**: planned as deferred, and still deferred — now also raised by the
  reviewer. See Deferred.
- Everything else matches: tier, branch, endpoints, status codes, the 20-origin cap, schema
  names, migration shape, and frontend untouched.

### Blockers / Deferred
Logged, not fixed — none is a defect in what this slice built:
- **No Postgres verification of migration 0012** *at the time of this commit*. Verified only on a
  throwaway SQLite database. The dialect differences that matter are VARCHAR(255) enforcement
  (the source of finding 2, now fixed), native ENUM types, and `ALTER` vs. table-recreate.
  Now a standing requirement: `CLAUDE.md` §9.1 requires every migration to be verified on both
  SQLite and a scratch Postgres database that the check creates and drops.
- **Later slice, not now: the test suite cannot run against Postgres.** `tests/conftest.py`
  forces SQLite. It should accept a Postgres test-database URL by environment variable, so the
  full suite can run against the production dialect in CI. Until then, "223 passed" is evidence
  about SQLite only — which is exactly how B1's length bug stayed invisible.
- **`batch_alter_table` on SQLite recreates `website_integrations` from reflection**, and whether
  the three `sa.Enum` CHECK constraints survive depends on SQLAlchemy's SQLite CHECK reflection.
  Dev/test only; Postgres does a direct `ALTER ... SET NOT NULL`.
- **No `public_key` rotation path.** Deleting the integration is the only way to change the key,
  and that cascades away every registered origin. Once B8 embeds the key in customer pages, "the
  key leaked into a public repo" has no remedy. Cheapest to add before B2–B8 harden around it.
- **The origin cap is read-then-write**, so concurrent POSTs can land 21 rows. The unique
  constraint still prevents duplicates.
- **`public_key` has no `server_default`**, unlike the other defaulted columns in 0011: an insert
  bypassing the ORM would violate NOT NULL.
- **`/website-integration/origins` (singular alias) 404s.** The integrations router is mounted
  under both spellings; the origins router only under the plural.
- Three modules still carry private `_record_audit` copies (decision 3).

### Verification (2026-09-12, after the review fixes)
- Ruff: `All checks passed!`
- Backend, from the repository root: **223 passed** (172 pre-existing + 51 new).
- Frontend (untouched): `pnpm test` 108/108; `pnpm build` exit 0.
- Migration: `upgrade → downgrade → upgrade` on a throwaway SQLite database seeded with two
  pre-existing `website_integrations` rows — both backfilled with distinct non-null keys, NOT
  NULL and the unique index both enforced, rows intact after downgrade. Repeated after the review
  fixes.
- Evals: none exist yet.

---

## Step A · Slice — roadmap reconciliation (one numbering scheme)

**Rigour tier: 3 — Light** (CLAUDE.md §9.0): documentation only, no code touched.
**Status: COMPLETED** — merged to `main` on 2026-09-12.

### Objective
`FEASIBILITY.md` step A, "one roadmap". Three numbering schemes were live at once and collided:
the archived 19-phase roadmap (its Phase 04 is the knowledge base), this tracker's `01`–`12` plus
`A`/`B`/`B.1` (its Phase 09 is the knowledge base), and `FEASIBILITY.md` steps A–D with slices.
The third collision — legacy "Phase B.1" (frontend auth) against step B slice B1 — appeared while
writing the B1 entry above, and B2–B8 would each have hit it again.

### Completed Work
- **One forward scheme**: step + slice, from `FEASIBILITY.md` §3 and `STEP-<X>-SLICES.md`.
  Recorded in `CLAUDE.md` §3.4, which previously logged the collision as an open hazard.
- **`MVP-IMPLEMENTATION-ROADMAP.md` retired** to `docs/archive/` (`git mv`, history preserved)
  with a banner explaining that it is a map of scope and not a plan. Its last live citations were
  removed: `ANTIGRAVITY-PROJECT-RULES.md` ranked it #2 in the authority hierarchy — that
  hierarchy now starts at `CLAUDE.md` and no longer omits it, `MVP-REQUIREMENTS-V2` or
  `FEASIBILITY` — and `MVP-REQUIREMENTS-V2.md` cited "roadmap Phase 13".
- **This tracker**: a Step status table for A–D at the top; the phase table demoted to
  "historical record, never cited for new work"; Phase 11 corrected from PENDING to COMPLETED
  (it shipped, was remediated and is merged); Phase 12 marked SUPERSEDED by step B; the stale
  "Next Phase — halted awaiting instruction" note retired.
- **README**: "Current Status: Phase 01 Complete", eleven phases stale, replaced with an honest
  pre-MVP summary that points at `CLAUDE.md` §2 rather than repeating it — duplication is how it
  drifted — plus corrected doc links and repository structure.
- The root Phase 01 implementation prompt is marked historical.

### Architectural & Technology Decisions
1. The step/slice scheme wins because it is the only one tied to what is actually being built and
   it already governs execution (`DEVELOPMENT-WORKFLOW.md` §2).
2. The roadmap is archived, not deleted: `FEASIBILITY.md` §2 calls it a fair map of the territory
   and a bad plan, and its scope enumeration is still worth having.
3. Legacy phase entries are kept verbatim rather than renumbered. Renumbering completed work
   would invalidate every commit message that cites a phase.

### Deviations
Checked against the proposed scope: none in the work itself. Two notes —
- The proposal listed `ANTIGRAVITY-PROJECT-RULES.md` only implicitly ("retire or subordinate the
  losing document"); its authority hierarchy had to change, since it ranked the archived roadmap
  above everything except the design phases.
- The optional `STEP-A-SLICES.md` (remaining step-A work: key removal, workspace clone+read, the
  05–08 decision) was **not** written — it was offered and not chosen, so it stays out. Step A's
  remaining slices therefore have no breakdown yet, which the Step status table now says plainly.

### Blockers / Deferred
- Design Phases 1–27 and `REFERENCE-ARCHITECTURE.md` still use their own phase numbering. They
  are design documents rather than plans, so they were left alone; if they start being cited for
  execution, they need the same treatment.

### Verification (2026-09-12)
- Ruff: `All checks passed!` (no code changed; run because §9.1 asks for it).
- Backend suite: unchanged from `9fe77f7` — **223 passed** — and re-run after these edits.
- `grep` for `MVP-IMPLEMENTATION-ROADMAP` outside `docs/archive/`: the only remaining mentions
  are inside historical log entries in this file, which describe what was true then.

---

## Step A · Slice — remove the development secrets from source

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared before work started. Credential
*plumbing*, not a credential path: no customer-repo write, no tenancy, no agent, prompt, model or
tool surface. The reviewer independently confirmed the tier.
**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; merged to `main`.

### Objective
`FEASIBILITY.md` step A: `SECRET_DEV_ENCRYPTION_KEY` and `JWT_DEV_SECRET` out of
`app/core/config.py` (CLAUDE.md §3.2). Development keys from the environment or a generated,
gitignored file; production behaviour unchanged and still failing loudly. Done before B2 because
the history-rewrite cost grows with every commit.

### Completed Work
- **`app/core/dev_secrets.py`**: `load_or_create_dev_secrets` generates `jwt_secret`
  (`token_urlsafe(48)`) and `encryption_key` (`Fernet.generate_key()`) on first use, one file per
  installation. Exclusive create with mode `0600` at creation rather than a chmod afterwards, so
  there is no window in which the key is world-readable — on POSIX. On Windows file modes do not
  map to ACLs, and the docstring says so rather than implying protection that does not exist. A
  concurrent process's file is adopted, never overwritten. A corrupt, incomplete or non-Fernet
  file raises an error naming the file and saying to delete it.
- **`config.py`**: both literals gone. `DEV_SECRETS_FILE` defaults to an absolute path anchored to
  the `backend` package, *not* the working directory — CLAUDE.md §8 documents two CWDs for one
  installation, and a relative default silently hands them different keys. Keys are generated only
  for development, dev, local, test and testing; any other `APP_ENV` (staging, unset, a typo) is
  refused rather than handed a per-process random key.
- **Production still refuses the leaked pair**, now by SHA-256 digest, so deleting the literals did
  not also delete the check that stops a stale `.env` being promoted to production.
- **`backend/scripts/verify_migration.py` plus `scripts/seeds/`**: the §9.1 migration rule made
  executable — upgrade, downgrade, upgrade on SQLite *and* on a scratch Postgres database it
  creates and drops, comparing schema snapshots so an asymmetric or lossy migration fails there.
  It uses a `fussion_migcheck` role (LOGIN CREATEDB, not superuser) via libpq's password file;
  never reads `backend/.env`, never touches `fussion_db`, never prints a connection string. Each
  dialect runs in its own interpreter, because `Settings` is built at import and the second dialect
  would otherwise migrate the first one's database — a bug this script's own first run exposed.
- **Migration 0012 is now verified on Postgres too**, seeded with pre-existing rows.
- Secondary: a failed credential decryption is logged rather than silently swallowed (reachable now
  that dev keys differ per installation); `conftest.py` assigns per-run keys so no test reads or
  writes a developer's file; `.gitignore`, `backend/.env.example` and `CLAUDE-CODE-SETUP.md`
  updated — the last still described `SECRET_DEV_ENCRYPTION_KEY` as the live key.

### Architectural & Technology Decisions
1. A generated per-installation file rather than a committed placeholder: a default in source is a
   default that ships, which is how this hazard was created.
2. Known-compromised values are denied by digest, not plaintext. The plaintexts are already public
   in `f4027e0`, so the digests leak nothing, and this keeps the check without keeping the secret.
3. `DEV_SECRETS_FILE` must end with `.dev-secrets.json`, the name `.gitignore` covers, so
   redirecting it cannot produce a committable secret.
4. Generation is an allowlist of environments, not "anything that is not production". A denylist
   would hand staging a fresh key per replica: 401 loops and unreadable ciphertext.

### Review history
One round (Tier 2 gate) — **PASS WITH FINDINGS**, no BLOCKING finding. All five SHOULD FIX items
were defects in what this slice built, and are fixed here with tests:
1. **The test file re-added both leaked plaintexts** — in the very commit that removes them, and
   the guard test scanned `app/` only, so it structurally could not see its own file. The
   plaintexts are gone; the guard now scans app, tests, alembic, scripts and docs; the denial
   mechanism is exercised through a planted stand-in digest instead.
2. Digests were restated in the test — now imported from `config`, so a third entry cannot leave
   the guard checking only the old two.
3. `DEV_SECRETS_FILE` was relative to the working directory (decision above).
4. `chmod` after writing left a readable window, and does nothing on Windows.
5. An unrecognised `APP_ENV` generated ephemeral keys (decision above).

Four CONSIDER items were also taken: Fernet validation inside `_read`, the gitignore-coupling
guard, `conftest` assignment instead of `setdefault`, and the stale `CLAUDE-CODE-SETUP.md` text
plus deny entries for the new file.

### Deviations
Checked against the owner's instruction and the plan:
- **Scope grew twice, both deliberately.** `backend/scripts/verify_migration.py` and its seed
  module are the owner's separate instruction (promote the Postgres check, reference it from §9.1),
  landed in this commit rather than a third one. The review fixes then widened the diff again.
- `app/core/errors.py`, `pyproject.toml` and `uv.lock` are **not** in this commit; they belong to
  B1 (`f8cc086`).
- Two documented realities rather than fixes: on Windows the generated file is not ACL-protected,
  and one installation has two documented working directories, which is why the default is
  anchored to the package.
- The `CLAUDE.md` §3 step-A table asserts this item done; it lands in the same commit as the code,
  not ahead of it. The reviewer caught the tracker lagging while `CLAUDE.md` already claimed
  completion — exactly the §10 pattern — which is why this entry exists.

### Blockers / Deferred
- **The git-history rewrite is unchanged, and still the hard blocker on the first push.** Both
  values remain in `f4027e0`, and every commit makes the rewrite larger.
- **A development database still holding tokens encrypted under the old key cannot read them.**
  Re-enter the token, or set `SECRET_ENCRYPTION_KEY` to the old value accepting that it is
  compromised. The failure is now logged, but the *user-facing* message still says "fix your widget
  path" — the `GET /plan` hazard already logged in CLAUDE.md §3.
- **No entropy floor on production keys.** `JWT_SECRET_KEY=q` is accepted, and the digest denylist
  is exact-match, so a leaked value with a character appended also passes. The error messages no
  longer claim otherwise. A length or entropy check is its own slice.
- **`ruff` does not enforce the declared `line-length = 100`**: no `[tool.ruff.lint] select` is
  configured, so `E501` is not in the default rule set, and "ruff clean" is weaker than it reads.
  Enabling it surfaces **360** pre-existing violations, so it is its own cleanup slice; the lines
  this slice and B1 added were wrapped by hand.
- **`is_production` is still a two-string check** on the database-URL path, so an unrecognised
  `APP_ENV` still falls back to SQLite. Narrowed for keys here, not for the database.
- Three modules still carry private `_record_audit` copies (from B1).

### Verification (2026-09-12)
- Ruff: `All checks passed!` across `backend/app backend/tests backend/scripts`.
- Backend, from the repository root: **254 passed** (238 before the review fixes, then 16 further
  tests for the fixes). Red first: 3 failed and 5 errored before the code existed.
- Migration 0012 via `backend/scripts/verify_migration.py --seed ...`: **SQLite and Postgres both
  green**, scratch database created and dropped, none left behind.
- Smoke test outside the suite: JWT and Fernet round-trips against a generated file, and the key is
  not the leaked one.
- Frontend: **not run, and not claimed** — no frontend file is in this diff.
- Evals: none exist yet.
