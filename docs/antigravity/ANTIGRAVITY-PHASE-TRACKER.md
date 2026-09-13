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
| **A. Truth & safety** | layout-overwrite fix, workspace clone+read, one roadmap, key removal, 05–08 decision | **COMPLETE** — layout-overwrite fix, roadmap reconciliation, dev-secret removal from source and the git-history rewrite (2026-09-12), the `@/` alias fix and the 05–08 decision all done; the last item, `SandboxProvider` + workspace rename, landed as **C14** |
| **B. Runtime plane** | `STEP-B-SLICES.md` B1–B8 | **IN PROGRESS** — B1 (`95b63eb`) through B6 done; **B7 (SSE) and B8 (real widget + customer-origin CORS) remain**. The owner's B7 deferral is re-scoped as an MVP gap in `GAP-CLOSURE-PLAN.md` (acceptance #8 names a *streamed* answer); B7 precedes B8 |
| **C. Analyst + harness + skills + evals** | WebsiteAnalyst, thin harness, tool gateway, 2 skill packages, 5-case eval corpus | **COMPLETE** — C1–C15 done. The remaining MVP gaps are step B (B7 SSE, B8 widget) per `GAP-CLOSURE-PLAN.md`; step D stays post-MVP |
| **D. Coding agent** | write capability, generated-code scan, ChangeSet → PR, bounded repair | NOT STARTED — no slice breakdown yet; post-MVP per `FEASIBILITY.md` §4 (the deterministic PR path already covers acceptance #6) |
| **E. GitHub App connection** | `STEP-E-SLICES.md` E1–E2 (planned) | NOT STARTED — the Railway-style connect flow, replacing the pasted PAT. Post-MVP per `MVP-REQUIREMENTS-V2.md` scope item #3; sequenced after the pipeline is validated on a real repository. See `GAP-CLOSURE-PLAN.md` Phase 6 |

The gap between the code and the Part C acceptance criteria, and the ordered path to close it, is
`docs/implementation/GAP-CLOSURE-PLAN.md`. Slice definitions live in the `STEP-*-SLICES.md` files;
the plan only sequences them.

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

**Status: COMPLETED** — fussion-reviewer round 2 PASS WITH FINDINGS; committed as `dd10167` and
merged to `main` on 2026-09-12 (fast-forward). Phase 11 code was already running (the table above
still says PENDING; reconciling the table and the two roadmaps is its own step-A slice, and is
the next one). Baseline commit `1034f4a`.

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
- **Resolved (2026-09-12): the leaked dev secrets were rewritten out of git history**
  (`git filter-repo --replace-text`, before any remote was added). They remain compromised —
  rotate anything they protected. Every pre-rewrite SHA changed, so older entries in this file
  cite hashes that no longer exist; they were remapped to the new ones. CLAUDE.md §3.2.
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
    fixture/workspace paths depend on the working directory (a clean checkout of `1034f4a`
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
`95b63eb` and merged to `main` on 2026-09-12, along with `fix/layout-overwrite` (the §3.1 fix),
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
- Backend suite: unchanged from `b00a2d8` — **223 passed** — and re-run after these edits.
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
   in `1034f4a`, so the digests leak nothing, and this keeps the check without keeping the secret.
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
  B1 (`95b63eb`).
- Two documented realities rather than fixes: on Windows the generated file is not ACL-protected,
  and one installation has two documented working directories, which is why the default is
  anchored to the package.
- The `CLAUDE.md` §3 step-A table asserts this item done; it lands in the same commit as the code,
  not ahead of it. The reviewer caught the tracker lagging while `CLAUDE.md` already claimed
  completion — exactly the §10 pattern — which is why this entry exists.

### Blockers / Deferred
- **The git-history rewrite is unchanged, and still the hard blocker on the first push.** Both
  values remain in `1034f4a`, and every commit makes the rewrite larger.
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

---

## Step A · Slice — archive the Antigravity project rules, carry forward what was still true

**Rigour tier: 3 — Light** (CLAUDE.md §9.0): documentation only, no code touched.
**Status: COMPLETED** — merged to `main` on 2026-09-12.

### Objective
`ANTIGRAVITY-PROJECT-RULES.md` was still a live authority while predating the agent
architecture, the requirements revision and the feasibility assessment. Read it end to end,
reconcile what was still true into the documents that are read every session, drop what
contradicted them, and archive the file beside the roadmap.

### Completed Work
Four rules were **not** in the current documents and are now carried:
- `CLAUDE.md` §4.10 — production fails loudly and never falls back: PostgreSQL is the system of
  record, SQLite is development and test only, and a missing or unacceptable secret raises at
  startup. Extended with what the key-removal slice added: keys are generated only for explicitly
  named development environments.
- `CLAUDE.md` §4.11 — the public surface is configuration-driven and reveals nothing internal:
  CORS from registered allowed origins, never `allow_origins=["*"]` in production; health
  endpoints return status only. **This binds B2 and B4 directly**, which is the main reason the
  reconciliation was worth doing before B2 rather than after.
- `CLAUDE.md` §6 — do not reinvent mature infrastructure (no custom ORM, auth primitive, queue,
  HTTP framework or logging), with the agent harness named as the one argued exception so it does
  not read as a general licence.
- `CLAUDE.md` §6 — inspect before modifying: the counterpart, for our own code, of §4.8 for a
  customer's.

Two things were dropped as **contradicting current scope**, recorded in the archive banner:
- Its YAGNI list forbade the sandbox and "advanced memory" that `MVP-REQUIREMENTS-V2` Part A pulls
  *into* MVP scope. Part D's register replaces it and carries a trigger per exclusion.
- "Business is the primary tenant" contradicts the canonical `Organization → Project → resources`
  hierarchy (Part A #1).

The rest was already covered: §2's plane, orchestrator and sandbox boundaries by `CLAUDE.md`
§4.1–§4.6, §5 and `AGENT-ARCHITECTURE` §8; §3.3 by §6; §4's secrets and tenant-isolation rules by
§4.1 and §9.1; §5's phase discipline by `DEVELOPMENT-WORKFLOW` §2 and §9.1.

The file moved to `docs/archive/` with a banner mapping every section to its disposition. Its live
citations were updated: the README now points at the requirements document and lists both archived
files as non-authorities, and the historical Phase 01 prompt points at the new path. Mentions
inside this tracker's own historical log entries were left alone, since they describe what was
true then.

### Architectural & Technology Decisions
1. Invariants were **appended** as §4.10 and §4.11 rather than renumbered into the middle. §4.8
   and §4.9 are cited by name in `CLAUDE.md` §3, the tracker and `AGENT-ARCHITECTURE`;
   renumbering would silently invalidate those references.
2. Archived rather than deleted, with a per-section disposition table, so the question "where did
   rule X go?" has a written answer instead of requiring a git-history search.

### Deviations
Checked against the instruction:
- The instruction said "anything that contradicts the current docs gets reconciled". Two items
  contradicted and were dropped rather than carried, which is recorded in the banner rather than
  silently omitted.
- Also updated, though not named: the README's governance list (it linked the file as live) and the
  root Phase 01 prompt (a stale path).
- Design Phases 1–27 and `REFERENCE-ARCHITECTURE.md` were left alone — see the report below.

### Blockers / Deferred
Reported to the owner in the same session, and deliberately **not** fixed:
- `Claude outputs/fussion-reviewer.md` is a byte-identical duplicate of
  `.claude/agents/fussion-reviewer.md`. Nothing loads it; the risk is that someone edits the
  visible root copy while the gate keeps using the other.
- `AGENT-ARCHITECTURE.md` carries stale *status* claims: §16 still lists "Phase numbering … must
  reconcile", and §15's step A still lists "one roadmap" and "remove the hardcoded dev encryption
  key" as pending. Its normative content is consistent; only the status lines have drifted.
- Roughly twenty citations to Design Phases 1–27 across `AGENT-ARCHITECTURE.md` and `ADR-001`
  point at documents that are not in the repository, and constitute a fourth numbering scheme.
- `frontend/AGENTS.md` is regenerated by `next dev` and will keep reappearing in diffs.

### Verification (2026-09-12)
- Ruff: `All checks passed!` (no code changed).
- Backend suite: unchanged from `7a9d10c` — **254 passed**.
- `grep` for `ANTIGRAVITY-PROJECT-RULES` outside `docs/archive/`: only this tracker's historical
  entries and the two updated pointers remain.
- Frontend: not run, and not claimed — no frontend file changed.

---

## Step B (FEASIBILITY §3) · Slice B2 — runtime tenant resolver

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared before work started and unchanged. The
resolver is the runtime plane's tenancy boundary: it decides which organization a public request
belongs to, and every later runtime call derives its scope from that decision. A tenancy defect
here is a cross-tenant data path, which is the reason B4 deliberately precedes B5 — see
`STEP-B-SLICES.md` Notes.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; the one in-slice
finding fixed and re-verified. No endpoint, migration or schema change; committed with this entry.

### Objective
FR-108, with FR-107's key and origins made useful: a function turns an untrusted `public_key` and
`Origin` header into a trusted `TenantContext`, or refuses. Cross-tenant combinations fail.
Unknown key, unregistered origin and an origin registered to a different integration are
indistinguishable to the caller. **No behaviour exposed:** B4 is the first endpoint that calls it.

### Completed Work
- **`app/runtime/`** (new package, per `AGENT-ARCHITECTURE` §9). Its `__init__` records the layer
  rule: the visitor data plane must not import `app/agents/` or engineering tools.
- **`TenantContext`** (`app/runtime/resolver.py`): `organization_id`, `project_id`,
  `integration_id`, `origin`. Frozen and slotted, constructed only from server state, so no later
  stage — model output in particular — can widen its scope.
- **`TenantResolutionError`**: one exception, one constant message. Every refusal reaches it:
  missing/empty key or origin, malformed origin, and no match all take the same path.
- **`resolve_tenant(db, public_key, origin)`**: normalises the header with B1's `normalize_origin`,
  then runs **one** joined query filtering on `public_key` *and* the canonical origin, with the
  origin scoped to the key's own integration. Joining rather than branching is what makes the
  three refusal causes structurally indistinguishable.
- **Tests** (`tests/test_tenant_resolver.py`, 20): written red-first — the module failed to import
  before the code existed. Cover successful resolution and tenant-correctness; origin
  normalisation before matching; immutability of the context; and refusal of unknown key,
  unregistered origin, cross-integration origin, the cross-tenant combination (with the correct
  pair still resolving), and missing/malformed key or origin. One test asserts all four refusal
  invocations share a single exception type and message.

### Architectural & Technology Decisions
1. **No FastAPI dependency in the resolver.** It raises a domain exception and lets B4 map it to a
   status. That keeps the tenancy decision unit-testable without an HTTP surface and keeps
   `app/runtime/` from coupling to the API layer.
2. **Reuse `app/core/origins.normalize_origin`; no second implementation.** B1's log (decision 1)
   and its docstring both name B2 as the consumer, precisely so the stored and presented forms
   cannot drift.
3. **`raise ... from None` on the malformed-origin path**, so the underlying `ValueError` cannot
   surface as a distinguishable cause.
4. **No readiness/status gate.** A `NOT_CONNECTED` integration still resolves; resolution is about
   tenancy, not whether the assistant is configured. B4 decides what readiness it requires (YAGNI).
5. **Removable by deletion:** removing `app/runtime/` removes the capability; nothing else imports
   it yet.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. No §4
invariant violated; the anti-enumeration property was confirmed to hold as the code runs, not just
as asserted. One in-slice finding, fixed per §9.0:
1. The indistinguishability test asserted equality for only two of the three refusal causes the
   slice names; the cross-integration case asserted refusal alone. The test now proves all four
   refusal invocations share one exception type and message.

Three CONSIDER items, logged as gates on B4 rather than fixed now (the endpoint that would make
them reachable does not exist):
- `public_key` is passed to the query without a length or prefix bound. It becomes an
  unauthenticated public input at B4; the bound belongs in B4's request schema, as
  `AllowedOriginCreate` bounds its raw input.
- B4 must map `TenantResolutionError` to exactly one status and body, with no per-cause branch, or
  it will re-open the enumeration channel this slice closed.
- No readiness gate on the resolved integration (decision 4) — a B4 product decision.

### Deviations
Checked against the slice contract in `STEP-B-SLICES.md`:
- One file beyond the two named: `app/runtime/__init__.py`, because a package requires it.
- No endpoint, migration, schema or frontend change, as the slice specifies.
- Everything else matches: tier, the refusal property, and the cross-tenant behaviour.

### Blockers / Deferred
- The three B4 gates above.
- **No `public_key` rotation path** (carried from B1): deleting the integration is still the only
  way to change the key. Cheapest to add before B8 embeds it in customer pages.

### Verification (2026-09-12)
- Ruff, from `backend/`: `All checks passed!`
- B2 tests red-first: collection error (`No module named 'app.runtime'`) before the code existed;
  **20 passed** after.
- Full backend suite, from the repository root (the §8 Postgres `.env` caveat): **393 passed**
  (20 new + 373 pre-existing).
- Migration: none. Frontend: untouched and not run. Evals: none exist yet.
- Note: the full suite was run before the review fix; the fix changed only the B2 test file, which
  was re-run green, and no application code changed after that run.

---

## Step B (FEASIBILITY §3) · Slice B3 — visitor session / conversation / message schema

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared before work started and unchanged. Schema
only: no endpoint, no service, no model call, and nothing writes the tables. The tier is 2 because
the slice adds a storage shape with no reachable behaviour; it becomes Tier 1 when B4 first reads
or writes it under a public request.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; both in-slice
findings fixed and re-verified. Committed with this entry.

### Objective
FR-056, FR-119–FR-121: the conversation-memory tier exists as its own store, with retention
fields and a deletion path, separate from engineering conversations. Nothing writes to it yet —
B4 is the first endpoint that does.

### Completed Work
- **`app/models/conversation.py`** — one aggregate file, as `knowledge.py` holds the knowledge
  aggregate:
  - `VisitorSession` — belongs to a `WebsiteIntegration`; carries the canonical `origin` it began
    under and `expires_at`, its TTL.
  - `Conversation` — belongs to a session; carries `retention_expires_at`, the content-retention
    window, deliberately independent of the session TTL (FR-056).
  - `Message` — belongs to a conversation; `role` (`VISITOR`/`ASSISTANT`) and `content`.
  - `MessageRole` enum; a composite index on `(conversation_id, created_at, id)`.
- **Registration** — `app/models/__init__.py`, and `WebsiteIntegration.visitor_sessions` with
  `cascade="all, delete-orphan"`.
- **Migration 0013** — `visitor_sessions`, `conversations`, `messages`; FK `ondelete="CASCADE"`;
  the native `message_role` enum dropped in `downgrade()` on Postgres.
- **Tests** (`tests/test_visitor_conversations.py`, 10) — round trip and tenancy path, ordering,
  the enum, both retention fields required, the three cascade paths (integration, project,
  conversation), cross-tenant isolation of a cascade, and deterministic ordering on tied
  timestamps.

### Architectural & Technology Decisions
1. **Tenancy by path, not a column.** There is no `organization_id` on these tables; scope comes
   from `WebsiteIntegration → Project → Organization`, so it cannot drift from the integration's
   tenant. This is the runtime-plane counterpart of the resolver's `TenantContext`.
2. **Two retention timestamps, not one.** Session TTL and conversation retention are separate
   policies (FR-056 requires independent retention); collapsing them would force one policy on the
   other.
3. **Ordering is `(created_at, id)`.** `created_at` alone is not a total order — two turns written
   in one clock tick would read back arbitrarily. `id` breaks the tie, and the index includes it.
4. **`MAX_ORIGIN_LENGTH` is imported, not re-declared.** B1's review finding 3 was exactly this
   duplication across a module boundary; the column reuses the constant.
5. **The cascade that deletes is the ORM relationship cascade.** SQLite runs with the
   `foreign_keys` pragma off, so the migration's `ondelete` is inert there; it is a Postgres
   backstop. Recorded in the module docstring so a future bulk retention sweep does not silently
   orphan rows on SQLite.
6. **No `last_seen_at`.** Added, then removed after review: it duplicates `BaseModel.updated_at`
   and has no consumer until B4 (YAGNI). `expires_at` is the retention field the slice requires.

### Review history
One round (Tier 2 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. Two
in-slice findings, fixed per §9.0:
1. **Message ordering was not a total order.** `order_by="Message.created_at"` with an
   application-side clock could return a visitor turn and its reply in either order when written
   in the same tick. Now ordered by `(created_at, id)`, with the index extended to match, and a
   regression test on tied timestamps.
2. **The deletion path rested on the ORM, not the constraint, and this was implicit.** The
   reviewer's point stands: on SQLite the FK `ondelete` does nothing, so the passing cascade tests
   prove the ORM relationship, not the migration. Resolved by the reviewer's first option —
   keeping deletion ORM-only and saying so — documented in the module docstring and logged below
   as a gate on the retention sweep.

Also removed from CONSIDER: `last_seen_at` (decision 6). Two CONSIDER items were accepted without
change: `origin` is unindexed (no B4 consumer yet), and `passive_deletes` is not set, so a
control-plane delete loads children into the ORM (acceptable at current volume; see Deferred).

### Deviations
Checked against the slice contract in `STEP-B-SLICES.md`:
- One column removed after review (`last_seen_at`, decision 6) and one index widened (finding 1);
  both are the same three tables the slice names.
- No endpoint, service, schema, or frontend change, as the slice specifies.
- Everything else matches: tier, the three entities, and the retention fields.

### Blockers / Deferred
- **Retention enforcement (FR-119) is not built** — only the fields exist. The sweep is a later
  slice; it must delete through the ORM or enable the SQLite `foreign_keys` pragma, or it will
  orphan rows on SQLite while Postgres cascades.
- **SQLite foreign keys are off repository-wide.** The suite exercises ORM cascades, not the DB
  constraints; a dialect divergence in any `ondelete` is invisible to it. Enabling the pragma is
  its own change.
- **`passive_deletes` not set.** A control-plane delete loads all child rows; fine at current
  volume, revisited if runtime conversation history grows large.
- **FR-098 fencing is a B4 obligation.** `Message.content` is visitor-authored untrusted data;
  nothing reads it yet.

### Verification (2026-09-12)
- Ruff, from `backend/`: `All checks passed!`
- B3 tests: **10 passed**.
- Full backend suite, from the repository root: **403 passed** (10 new + 393 pre-existing).
- Migration 0013: `upgrade → downgrade → upgrade` verified on **both SQLite and a scratch
  Postgres database** (created and dropped; `fussion_migcheck` role with `LOGIN CREATEDB`). This
  closes the standing §9.1 gap B1 logged as a blocker. No seed: the migration creates new tables
  and backfills nothing.
- Frontend: untouched, not run. Evals: none exist yet.

---

## Step B (FEASIBILITY §3) · Slice B4 — public chat endpoint, no model

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared before work started and unchanged. This is
the runtime plane's first reachable surface and it resolves tenancy for unauthenticated public
traffic; a tenancy defect here is a cross-tenant data path.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; all three
in-slice findings fixed and re-verified. Committed with this entry.

### Objective
FR-107/FR-108/FR-113/FR-114: a real public endpoint that resolves the tenant from the public key
and `Origin`, is rate-limited, persists the conversation, and returns a canned reply. No model —
B5 replaces the reply; B6 inserts retrieval before it.

### Completed Work
- **`app/runtime/rate_limit.py`** — in-process fixed-window limiter (`RateLimiter.check`,
  `RateLimitExceeded`, `reset`). Bounded memory with oldest-window eviction at the cap.
- **`app/runtime/chat.py`** — `handle_chat(...)`: resolve tenant (B2) → IP limit → integration and
  organization limits → resolve/create session + conversation → session limit → persist visitor
  and assistant messages → return `ChatReply`. No FastAPI import; testable without HTTP.
- **`app/schemas/public_chat.py`** — `ChatRequest` (`public_key` bounded to 64, `message` bounded
  to 4000 and non-blank), `ChatResponse`.
- **`app/api/v1/endpoints/public_chat.py`** — `POST /api/v1/public/chat`, unauthenticated;
  `TenantResolutionError` → one 403 body (the B2 gate); `RateLimitExceeded` → 429 + `Retry-After`.
- **`app/api/v1/router.py`** — public router under `/public`.
- **`app/core/config.py`** — `PUBLIC_*` session TTL, retention and rate-limit settings.
- **`app/core/errors.py`** — 429 code mapping; **preserves `HTTPException.headers`** on the JSON
  error response (see Deviations — this fixed a pre-existing defect).
- **Tests** (`tests/test_public_chat.py`, 19) — happy path and reuse, canned reply from the
  Assistant and the fallback, tenancy refusals indistinguishable, missing/cross origin refused,
  foreign and expired sessions start fresh, origin binding, tenant-scoped persistence, IP /
  integration / organization / session limits, input bounds, and public-key capability separation.

### Architectural & Technology Decisions
1. **CORS for customer origins is deferred to B8.** The app's global `CORSMiddleware` intercepts a
   customer preflight before the handler runs, so per-origin CORS is its own security-sensitive
   change and belongs with the real widget and the CSP/origins documentation (FR-111). Agreed with
   the owner; logged as a B8 gate.
2. **Rate limiting is per-process, in-memory.** Honest for a single-process MVP; wrong across
   workers, where the effective limit multiplies by the replica count. Redis is the trigger-named
   replacement (CLAUDE.md §6) — no Redis exists.
3. **IP, integration and organization are the enforceable scopes.** The session scope is
   documented as *not* an abuse boundary: there is no server-set cookie, so a caller that omits or
   fabricates `session_id` gets a fresh counter. A conversation scope would duplicate the session
   one at MVP and is deferred to B5's usage accounting.
4. **Session reuse requires the same integration *and* the same registered origin.** `origin` was
   stored in B3 "so a later turn can be bound to it"; B4 is that turn. Same-integration, so never
   cross-tenant, but it stops a session begun on one registered origin being continued from
   another.
5. **The public key is not a credential for anything but chat.** The endpoint carries no auth
   dependency and reaches no control-plane resource (FR-114); a test asserts the key is not a
   bearer token.
6. **The canned reply is the tenant's `Assistant.welcome_message`**, falling back to a fixed
   string. Reading the Assistant now exercises the tenant → project → assistant path B5 will use.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. No §4
invariant violated; the reviewer traced `_resolve_or_create_session` and confirmed no
client-supplied session id can cross tenants, and confirmed the anti-enumeration body is
identical. Three in-slice findings, fixed per §9.0:
1. **Origin binding was not enforced.** `VisitorSession.origin` was written but never compared, so
   a session could be resumed from a different registered origin of the same integration. Now
   compared before reuse; test added.
2. **The session rate-limit scope was presented as an abuse boundary but is client-resettable**,
   and two of FR-113's five levels (organization, conversation) were absent with no deferral. The
   organization scope is now enforced; the session scope's limitation is documented in the code;
   the conversation scope is deferred to B5 with a reason. IP and organization tests added.
3. **The rate-limiter memory comment overclaimed.** It said buckets were "pruned rather than
   allowed to grow without limit", but pruning frees nothing while every bucket is inside its
   window. The map now evicts the oldest window at the cap, and the comment matches.

CONSIDER items accepted: `request.client.host` is the safe IP source (raw `X-Forwarded-For` is
spoofable); behind a proxy a trusted `ProxyHeadersMiddleware` is required, documented rather than
changed. FR-098 fencing is unreachable until B5 builds a prompt — logged as a B5 gate, not closed
here. FR-119 retention enforcement remains a B3 deferral.

### Deviations
Checked against the slice contract in `STEP-B-SLICES.md`:
- **`app/core/errors.py` changed for a pre-existing defect B4 surfaced.** The custom HTTP error
  handler rebuilt the response with `create_error_response`, dropping any headers the raise site
  attached. So the 429's `Retry-After` — and, already, the `WWW-Authenticate` on every 401 — never
  reached the client. The handler now forwards `exc.headers`. No existing behaviour regresses; the
  full suite is unchanged.
- **Organization rate-limit scope and IP/organization tests added after review** (finding 2), and
  origin binding after review (finding 1). Both are within the endpoint the slice names.
- **CORS not implemented**, by explicit agreement, deferred to B8 (decision 1).
- Everything else matches: tier, the public path, no model, no migration, no frontend.

### Blockers / Deferred
- **CORS for customer origins** — B8.
- **Conversation rate-limit scope** — B5 (usage accounting), or a later slice.
- **FR-098 context fencing** — B5, when a prompt first contains visitor messages.
- **FR-119 retention enforcement** — the sweep is still unbuilt (B3 deferral).
- **Rate limiting is per-process** — a multi-worker deployment needs Redis or a shared store.
- **IP source behind a proxy** — needs trusted `ProxyHeadersMiddleware`; do not switch to raw XFF.

### Verification (2026-09-12)
- Ruff, from `backend/`: `All checks passed!`
- B4 tests: **19 passed**.
- Full backend suite, from the repository root: **422 passed** (19 new + 403 pre-existing).
- Migration: none. Frontend: untouched, not run. Evals: none exist yet.

---

## Step B (FEASIBILITY §3) · Slice B5 — ModelProvider + ModelGateway

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared before work started and unchanged. The
widget now gets a real LLM answer; this slice introduces the model plane and the per-organization
cost boundary.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; all five
in-slice findings fixed and re-verified. Committed with this entry.

### Objective
FR-071–FR-075, FR-125: the widget gets a real LLM answer through a `ModelGateway` that enforces
allowed models, context and token caps, timeouts, bounded retries, a per-organization spend budget,
and records usage per call. Provider: Google Gemini. No model configured → 503, never a fabricated
answer.

### Completed Work
- **`app/llm/base.py`** — the `ModelProvider` seam: `ModelMessage`/`ModelRequest`/`ModelResponse`/
  `Usage` DTOs and the transient/permanent provider-error split. Fussion's types, not a vendor's.
- **`app/llm/gateway.py`** — `ModelGateway`: allowlist, context cap, budget check, timeout +
  bounded retries, usage recording; typed errors mapped to HTTP by the endpoint.
- **`app/llm/providers/gemini.py`** — the only module importing `google-genai` (lazily), mapping
  the SDK onto the DTOs and its errors onto the transient/permanent split.
- **`app/llm/providers/fake.py`** — deterministic test double (records requests, can fail on
  demand).
- **`app/llm/pricing.py`** — per-1M-token price table → estimated cost.
- **`app/llm/factory.py`** — builds the gateway from settings; `validate_model_configuration`
  refuses an inconsistent config at startup.
- **`app/models/model_usage.py` + migration 0014** — append-only usage ledger, org-scoped;
  project/integration/conversation links are `SET NULL` so a paid call is never erased by deleting
  its subject.
- **`app/runtime/chat.py`** — the canned reply is replaced by the gateway call: trusted system
  prompt + bounded conversation history; assistant reply and usage persisted.
- **`public_chat.py`/`errors.py`/`config.py`/`main.py`** — model-error → HTTP mapping (503/502/413/
  402), `MODEL_*` settings, gateway configured in `lifespan`.
- **Tests** — `tests/test_model_gateway.py` (15) and the updated `tests/test_public_chat.py` (23).

### Architectural & Technology Decisions
1. **Gemini via `google-genai`, imported only in the provider module.** `pydantic_ai` is *not*
   introduced in B5; the agent layer's framework decision (ADR-001) belongs to step C and plugs
   into this same seam.
2. **Fail loud, never fabricate.** No `MODEL_API_KEY` → the gateway is unconfigured and the runtime
   returns 503 (CLAUDE.md §4.10). Tests install a fake gateway explicitly, mirroring the git
   provider.
3. **Budget is projected before the call, not just checked after.** The call's maximum estimated
   cost is added to month-to-date spend; a call that would cross the limit is refused first.
   Warning / throttle / suspend thresholds per FR-074; throttle reduces `max_output_tokens`.
4. **A timeout is terminal, not retried.** A timeout is ambiguous — the provider may have completed
   and billed — so retrying could double-charge. Only explicit transient errors (429/5xx) retry.
5. **Usage is a ledger, not a column.** One append-only row per call keeps FR-073/FR-075 measurable
   and survives the deletion of the project or conversation that produced it.
6. **`CLAUDE.md` §5 clarified.** The "only `app/tools/` touches the database" rule is scoped to the
   agent layer; the control plane, `app/services/`, the runtime plane and the gateway's accounting
   access the database directly by design. The literal rule was already contradicted by
   `app/services/` and `app/runtime/` (B2–B4), and AGENT-ARCHITECTURE §2 places cost accounting in
   the gateway.
7. **Thinking disabled (`MODEL_THINKING_BUDGET=0`).** Gemini 2.5 bills "thinking" tokens as output
   but omits them from `candidates_token_count`, so leaving it on inflates recorded cost and can
   consume the output budget — a live 10-token budget returned no text at all because thinking ate
   it. The runtime is grounded Q&A, not reasoning. Verified against the live API.
8. **A second provider proves the seam (FR-072).** `OpenAICompatibleProvider`
   (`app/llm/providers/openai_compatible.py`, the only module importing the `openai` SDK) serves
   Moonshot/Kimi, OpenAI and OpenRouter via `MODEL_BASE_URL`. Switching vendors is configuration,
   not code. Kimi counts reasoning tokens inside `completion_tokens`, so its cost is honest without
   a thinking toggle.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. FR-125 and
FR-098 were verified positively (SDK confined to the adapter; visitor content stays in user turns).
Five in-slice findings, fixed per §9.0:
1. **Budget was non-atomic.** Spend was read before the call and written after, so a call starting
   just under the limit overshot it. The call's projected cost is now checked first. A residual
   concurrency overshoot remains (N in-flight calls can pass on the same pre-call sum); it is
   bounded by the per-org rate limit and documented in `_check_budget` as a gate on an atomic
   reservation.
2. **A `None` spend limit failed open silently.** `validate_model_configuration` now refuses an
   uncapped production configuration at startup; the gateway logs loudly when it runs uncapped.
3. **A retry could double-charge after a timeout.** Timeouts are now terminal (decision 4).
4. **`ModelNotAllowedError` was uncaught.** Startup validation refuses a `MODEL_ID` outside the
   allowlist; the endpoint also maps it to a legible 503 rather than a 500.
5. **`app/llm/` touched the database, against §5 as written.** Resolved by scoping §5 to the agent
   layer (decision 6) rather than by moving the access to another layer that is equally outside
   `app/tools/`.

CONSIDER logged, not fixed: the request's DB session is held across the model call (up to
~3 × timeout), so a burst of slow chats ties up pool connections — the same shape as the
`studio_events.py` leak (§3.6). Fixing it means releasing the session during the call and accepting
that the visitor message persists even when the model fails; that is a resilience slice.

### Deviations
Checked against the slice contract in `STEP-B-SLICES.md`:
- **`CLAUDE.md` §5 amended** (decision 6) — a governance change, recorded here rather than made
  silently.
- **`tests/test_public_chat.py` reply tests replaced.** The B4 canned-reply tests are superseded by
  model-reply tests; the endpoint's tenancy/rate-limit tests are unchanged.
- **`google-genai` added** to `pyproject.toml`/`uv.lock`, lazily imported.
- Everything else matches: tier, one provider, no streaming, no retrieval, no migration beyond the
  usage ledger.

### Blockers / Deferred
- **Atomic budget reservation** under concurrency — later slice (needs a committed reservation or a
  shared store).
- **DB session held across the model call** — resilience slice.
- **FR-089/FR-090 reproducibility** — no prompt hash and no provider-reported model version are
  recorded; `ModelUsage` stores the requested model id only. The eval harness (step C) owns this.
- **Per-organization configurable limit** — only a platform default is enforced; a per-org override
  is a later control-plane slice.
- **`stream`** — B7. **Document fencing (FR-098)** — B6. **CORS** — B8.

### Verification (2026-09-12)
- Ruff, from `backend/`: `All checks passed!`
- Model gateway tests: **15 passed**; the two model-touching files together: **38 passed**.
- Full backend suite, from the repository root: **441 passed**.
- Migration 0014: `upgrade → downgrade → upgrade` verified on **both SQLite and a scratch Postgres
  database**. No seed: new table, no backfill.
- No test hits a paid API; the fake provider is genuinely substitutable.
- **Live provider smoke (not a test):** `GeminiModelProvider` returned `pong` against
  `gemini-2.5-flash` (`in=15 out=1`) with a real key, confirming the key and the adapter. The vendor
  has retired `gemini-2.0-flash` (404), so it was removed from `MODEL_ALLOWED_IDS` and pricing; the
  allowlist and the price table are now the same single model.
- **Second-provider smoke (not a test):** `MODEL_PROVIDER=moonshot`, `kimi-k2.6` returned `pong`
  (`in=24 out=28`) through `OpenAICompatibleProvider`, confirming FR-072 substitution end to end.
  `.env` (gitignored) currently points at Moonshot; Gemini remains available by switching
  `MODEL_PROVIDER`.
- Frontend: untouched, not run. Evals: none exist yet.

---

## Step B (FEASIBILITY §3) · Slice B6 — real embeddings + tenant-filtered retrieval

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared before work started and unchanged. The
runtime now grounds answers in the tenant's own documents; retrieval is a tenancy boundary.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; all four
in-slice findings fixed and re-verified. Committed with this entry.

### Objective
FR-109, FR-098, scope item #9: replace the lexical placeholder embeddings with a real semantic
provider, resolve the embedding model and dimension from the `KnowledgeBase` rather than a call-site
constant, and ground runtime answers in the tenant's documents with citations.

### Completed Work
- **`app/services/knowledge/embeddings.py`** — asynchronous `EmbeddingProvider` ABC; the
  deterministic hash provider (now a documented test/dev double); `build_default_embedding_provider`
  (from settings) and `get_embedding_provider` (from a stored model id); `validate_embedding_configuration`.
- **`app/services/knowledge/embeddings_gemini.py`** — the only embedding module importing a vendor
  SDK; `gemini-embedding-001` at 768 dimensions via `output_dimensionality`, unit-normalised,
  batched.
- **`KnowledgeBase.embedding_model` + `embedding_dimension`** and **`Message.citations`**; migration
  0015 with a `--seed` module (`scripts/seeds/0015_embedding_model_citations.py`).
- **`ingestion.py` / `retrieval.py`** — both resolve the provider from the KB's stored model and
  dimension; retrieval fails closed on a dimension mismatch.
- **`app/runtime/chat.py`** — tenant-filtered retrieval, a fenced context block in the user turn,
  citations on the reply and persisted on the assistant message.
- **`public_chat.py`/`schemas`** — `citations` in the response; embedding errors mapped to 503.
- **`deps.py`** — new knowledge bases take the configured provider's model and dimension.
- **Tests** — grounding, citations, fencing, tenant filter, persistence, embedding-failure 503,
  dimension-mismatch 503, factory/validation.

### Architectural & Technology Decisions
1. **Gemini embeddings (`gemini-embedding-001`, 768-d).** Moonshot exposes no embeddings API
   (403), and `text-embedding-004` is retired (404). Vectors are normalised in the adapter so the
   shared dot-product cosine stays correct.
2. **Dimension and model live on the `KnowledgeBase`.** Ingestion and retrieval both resolve them
   from the stored value — the connascence CLAUDE.md §6 named — so a query always uses the model
   the chunks were embedded with. A base embedded with one model cannot be silently queried with
   another.
3. **The ABC is now asynchronous.** A real embedding call is I/O; the deterministic double is
   `async` without awaiting anything, so it stays substitutable.
4. **Tests use the deterministic provider** (`conftest` forces `EMBEDDING_PROVIDER=deterministic`);
   the real provider is verified by a live smoke, never by the suite.
5. **pgvector is deliberately not here.** Full-scan cosine is adequate at a few hundred chunks
   (`STEP-B-SLICES` Notes); it is its own slice when volume demands it.
6. **FR-098 fencing.** Retrieved chunks are labelled data inside the final user turn; the system
   prompt is the only instruction region and tells the model to treat context as data and to say
   when it does not know.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. FR-109 and
FR-098 were verified positively. Four in-slice findings, fixed per §9.0:
1. **Embedding failures escaped as a 500.** `EmbeddingProviderError` is now mapped to 503 at the
   endpoint — retrieval runs before the model, so an embedding outage is a dependency failure, not
   an unhandled error.
2. **No startup validation of the embedding configuration.** `validate_embedding_configuration`
   now runs in `lifespan`, refusing an unknown provider, a non-positive dimension, or a
   non-`gemini-embedding…` model id.
3. (Part of 2.)
4. **Migration 0015's NOT NULL backfill was unverified against pre-existing rows.** A seed module
   now inserts a knowledge base and a message at revision 0014, and the migration was re-verified
   `upgrade → downgrade → upgrade` with `--seed` on **both SQLite and scratch Postgres**.

Also fixed from CONSIDER: the Gemini adapter batches (100 texts per request) so a large document
cannot exceed the per-request limit, and retrieval fails closed on a chunk/query dimension mismatch
rather than scoring every chunk 0 through the 0.0 threshold.

CONSIDER logged, not fixed: embedding calls bypass `ModelGateway`, so embedding spend is unmetered
and outside the per-organization budget; `RETRIEVAL_SCORE_THRESHOLD=0.0` means top-k always injects
chunks and grounding rests on the prompt; the provider is dispatched by model-id prefix, so the
stored spelling is coupled to resolution; the migration uses `sa.JSON()` while the model declares
the JSONB variant (pre-existing convention).

### Deviations
Checked against the slice contract in `STEP-B-SLICES.md`:
- The embedding ABC changed from synchronous to asynchronous; `test_knowledge.py`'s embedding test
  and the ingestion/retrieval call sites were updated accordingly.
- `tests/test_public_chat.py` gained a B6 section and its response-shape assertion.
- No pgvector, no streaming, no change to the control-plane knowledge endpoints beyond the KB
  fields.

### Blockers / Deferred
- **Embedding cost is unmetered** — the gateway budget covers generation only.
- **pgvector** — full-scan cosine until volume demands it.
- **Provider selection by model-id prefix** — store the provider name on the KB if a second
  embedding vendor lands.
- **`stream`** — B7. **CORS** — B8.

### Verification (2026-09-12)
- Ruff, from `backend/`: `All checks passed!`
- Full backend suite, from the repository root: **449 passed**.
- Migration 0015: `upgrade → downgrade → upgrade` verified with the `0015` seed on **both SQLite
  and a scratch Postgres database**.
- **Live embedding smoke (not a test):** `gemini-embedding-001`, 768 dimensions, unit norm, and
  semantic ranking (refund↔shipping 0.58 > refund↔photosynthesis 0.46).
- No test hits a paid API; the deterministic provider is genuinely substitutable.
- Frontend: untouched, not run. Evals: none exist yet.

---

## Step C (FEASIBILITY §3) · Slice C1 — retire the 05–08 contract layers

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. No
customer-repo, credential or cross-tenant path; the change deletes an unused subsystem.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; the tracker gap
and both CONSIDER items fixed. Committed with this entry.

### Objective
Execute the 05–08 decision (CLAUDE.md §3.5, 2026-09-12): **repurpose** the deterministic
read/inspection/detection substrate as the analyst's input, and **retire** the contract /
integration-plan / adapter / execution-plan layers that the MVP integration path never references.

### Completed Work
- **Deleted (backend):** models `contract`, `integration_plan`, `integration_adapter`,
  `execution_plan`; schemas `contract`, `integration_plan`, `integration_adapter`,
  `execution_plan`; services `contract`, `integration_planner`, `integration_adapter`,
  `execution_planner`; endpoints `contracts`, `integration_plans`, `integration_adapters`,
  `execution_plans`; tests `test_contracts`, `test_integration_plans`,
  `test_integration_adapters`, `test_execution_plans`.
- **Wiring removed:** the four snapshot relationships, the four `deps.py` resolvers, the four
  router includes, the eight `CONTRACT_*`/`INTEGRATION_PLAN_*`/`INTEGRATION_ADAPTER_*`/
  `EXECUTION_PLAN_*` permissions (and their role mappings), and the schema/model exports.
- **Migration 0016** drops `api_contracts`, `api_operations`, `integration_plans`,
  `integration_adapters`, `execution_plans` and the six Postgres enums; its `downgrade` recreates
  the exact 0007/0008 schema. 0007/0008 stay for the chain's history.
- **Frontend:** `DiagnosticsTab` stripped to the discovery section; the four API clients
  (`contracts`, `integration-plans`, `adapters`, `execution-plans`) deleted and un-exported; the
  Studio test updated.
- **Kept, as decided:** `workspace.py`, `acquisition.py`, `inspection.py` and the `discovery.py`
  detectors with `Repository`/`RepositorySnapshot`/`DiscoveryRun` — the read substrate C4/C8 build
  on.

### Architectural & Technology Decisions
1. **Drop, don't rewrite history.** 0007 and 0008 created tables that a released migration chain
   must still be able to walk; retiring them means a new migration that drops, never deleting the
   applied ones.
2. **Two similarly named things are not the same.** `IntegrationPlanPayload` and
   `IntegrationPlanner` (the MVP widget plan, `services/integration/planner.py`) and
   `ApiContractFinding` (a discovery finding) were deliberately kept; only the 05–08 `ApiContract`
   / `IntegrationPlan` / `IntegrationAdapter` / `ExecutionPlan` models were retired.
3. **The `DiagnosticsTab` sub-navigation collapses to one label** — with a single section left, an
   interactive control that does nothing is worse than a heading.

### Review history
One round (Tier 2 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. The reviewer
confirmed no dangling references (`import app.main`, mapper configuration, and `pytest
--collect-only` all clean) and that the 0016 `downgrade` is column-, default-, FK-, index- and
enum-faithful to 0007/0008. Fixed in-slice:
1. **Tracker gap:** this entry (CLAUDE.md §9.1).
2. (CONSIDER) the unused `discoveries` prop on `DiagnosticsTab` — removed.
3. (CONSIDER) the inert sub-navigation button — replaced with a non-interactive label.

### Deviations
Checked against `STEP-C-SLICES.md` C1:
- Everything the slice names was removed, and the drop migration keeps the chain reversible.
- The `Repository`/snapshot/workspace substrate was **kept**, not moved into a new package; moving
  it is deferred to C4, where its shape is decided by the tools that consume it.
- No new package layout (`app/services/analysis/`) was introduced; `discovery.py` stays where it is
  for now.

### Blockers / Deferred
- The remaining step-C gates are unchanged: a repository-read source for the tools (C4),
  `pydantic_ai` (C5), `skills-ref` (C7), frontend widget-target fixtures (C9).

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Backend suite, from the repository root: **421 passed** (the 28 tests of the four retired test
  modules removed; no other test changed).
- Migration 0016: `upgrade → downgrade → upgrade` verified on **both SQLite and a scratch
  Postgres database**.
- Frontend: `pnpm build` clean; `pnpm test` **108 passed**.

---

## Step C (FEASIBILITY §3) · Slice C2 — agent runtime substrate

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. This
introduces the tenancy carrier for the engineering plane.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; all three
in-slice findings fixed and re-verified. Committed with this entry.

### Objective
FR-046–049, FR-051, FR-089, FR-090: a declarative agent contract and registry, a frozen
`ExecutionContext` built only from trusted state, and `AgentRun` persistence with its ordered
tool-call log. No model call and no loop yet — those are C5/C6.

### Completed Work
- **`app/agents/base.py`** — `Budget` and `AgentDefinition` (name, version, instructions,
  capabilities, tools, output schema, budget). Pure data; no infrastructure.
- **`app/agents/registry.py`** — `AgentRegistry` resolving `(name, version)`, refusing a duplicate
  registration.
- **`app/harness/context.py`** — frozen `ExecutionContext` (org, project, repository, environment,
  agent, capabilities, `commit_sha`, run id), `has_capability`, `bind_run`, and a JSON `snapshot`.
- **`app/models/agent_run.py`** — `AgentRun` (status, step, attempt, prompt hash, model id +
  reported version, skill versions, budget, tokens, cost, context snapshot, failure class/reason,
  timestamps) and `AgentToolCall` (ordered, unique per run); migration 0017.
- **`app/harness/run.py`** — `start_agent_run`, `record_tool_call`, `finish_agent_run`,
  `record_run_metadata`.
- **`Project.agent_runs`** cascade, and registration in `models/__init__.py`.
- **Tests** (`tests/test_agent_runtime.py`, 12) — context immutability/snapshot, registry,
  run/context consistency, capability narrowing, metadata, ordered tool calls, failure class,
  cascade purge.

### Architectural & Technology Decisions
1. **The context is frozen and trusted-state only (FR-048/049).** `bind_run` returns a new context,
   so no stage can widen its own scope; `snapshot()` is the audit record stored on the run.
2. **A run verifies it belongs to its context.** `start_agent_run` refuses a context naming a
   different agent, and refuses capabilities the agent does not declare — while allowing a
   *subset*, which is the capability-narrowing FR-094 requires.
3. **`AgentRun` is the harness's own record, not a model capability.** `app/harness/run.py` touches
   the database; CLAUDE.md §5's exception list now names it explicitly rather than the code
   claiming an exception that was not written.
4. **`commit_sha` is on the context from the start.** C4's read tools need to read at a pinned
   revision; adding a field to a frozen slots dataclass later would churn every call site.
5. **The tool-call log is a table, not a JSON blob** — ordered by a unique `(run, sequence)`, so
   FR-090's reconstruction is a query.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. FR-046/048/049
were verified positively (the agent package imports no infrastructure; the context is immutable).
Three in-slice findings, fixed per §9.0:
1. **`run.py` claimed a §5 exception that did not exist.** CLAUDE.md §5 now names the harness's run
   record in its exception list, so the precedent is written rather than asserted.
2. **A run could be started for a context describing a different agent**, leaving the columns and
   the context snapshot inconsistent (FR-089) and the capability set unverified (FR-049).
   `start_agent_run` now verifies identity and refuses undeclared capabilities.
3. **FR-089 metadata was columns without a writer.** `record_run_metadata` writes prompt hash, model
   id, provider-reported version and skill versions, with a test.

CONSIDER fixed: `commit_sha` added to the context (see decision 4); duplicate agent registration now
raises. CONSIDER logged: `_next_sequence` is `MAX+1` and not atomic (sequential at C6); the entity
diverges from AGENT-ARCHITECTURE §3.0's `job_id`/`agent_id` and needs a decision before C6; FR-069
argument redaction is C3's obligation; `repository_id` is `SET NULL` on purpose so a run outlives
its repository.

### Deviations
Checked against `STEP-C-SLICES.md` C2:
- All named pieces exist; the persistence lives in `app/harness/run.py` as the architecture's module
  layout specifies, with the §5 exception now written.
- No `ProjectMemory` model and no budget enforcement — both are later slices (C6), as the notes
  allow.

### Blockers / Deferred
- **Budget enforcement** and **resumability** are C6. **Project memory (FR-058–062)** is C6.
- **FR-069 argument redaction** is C3's gateway obligation.
- The remaining step-C gates: repository-read source (C4), `pydantic_ai` (C5), `skills-ref` (C7),
  frontend fixtures (C9).

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Backend suite, from the repository root: **433 passed**.
- Migration 0017: `upgrade → downgrade → upgrade` verified on **both SQLite and a scratch Postgres
  database**.

---

## Step C (FEASIBILITY §3) · Slice C3 — the tool gateway

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. The
gateway is the authorization choke point for every tool an agent calls.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; all three
in-slice findings plus a consistency check fixed and re-verified. Committed with this entry.

### Objective
FR-064–070: a tool contract and registry, and one gateway that authorizes → executes → records.
Read tools are auto-authorized for an agent holding the capability; write tools additionally require
an approved plan.

### Completed Work
- **`app/tools/base.py`** — `ToolKind`, `ToolResult` (output, `truncated`, `error`, `denied`),
  `ToolError`, and the `Tool` ABC (name, model-facing description, kind, required capability, input
  schema, `execute(context, arguments)`).
- **`app/tools/registry.py`** — `ToolRegistry`, refusing a duplicate registration.
- **`app/tools/gateway.py`** — `ToolGateway`, `ApprovedPlan`, `redact_arguments`, `record_tool_call`.
  Authorization precedes execution; every path is recorded with an outcome
  (`ok`/`error`/`denied`/`unknown`).
- **Tool-call recording moved** from `app/harness/run.py` to the tools layer, so the dependency
  direction stays harness → tools and the tools layer (the DB layer per §5) owns the record.
- **Tests** (`tests/test_tool_gateway.py`, 25) — read auto-auth, denial without capability, write
  behind approval, unknown tool, invalid arguments, `ToolError`, unexpected exception, redaction
  (nested and key-name cases), truncation, scope from context, cross-tenant run rejection, registry.

### Architectural & Technology Decisions
1. **Authorization is a precondition, not a convention.** `_denial_reason` runs before validation
   and execution; a caller cannot reach `tool.execute` without passing the capability and approval
   checks.
2. **A denial is a result, an unknown tool is an error.** A denied call returns `denied=True` and is
   recorded as `denied`; an unknown tool is recorded as `unknown` and is recoverable. The C6 loop
   must treat `denied` as terminal — logged as a C6 gate.
3. **Redaction lives inside `record_tool_call`.** No caller can persist a secret by forgetting to
   wrap its arguments; matching is token-based so `path` survives while `api_key` and `X-Api-Key` do
   not.
4. **A run must belong to the context it is authorized against.** The gateway refuses a mismatched
   `(run, context)` pair, so a read cannot be authorized for one tenant and recorded on another.
5. **An unexpected tool exception is logged and hidden.** The model gets `"The tool failed
   unexpectedly."`; the operator gets the traceback.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. Three
in-slice findings, fixed per §9.0:
1. **`record_tool_call` stored arguments verbatim**, so redaction depended on every caller
   remembering to wrap. Redaction now happens inside the function; two existing callers that passed
   raw arguments are covered.
2. **The sensitive-key list was incomplete** (`auth`, `bearer`, `session`, `pat`, …), and a
   substring test would have redacted `path`. Matching is now token-based with a wider set.
3. **The unexpected-exception path discarded the exception.** It is logged server-side while the
   model still sees a generic message.

Also added from CONSIDER: the gateway now asserts the run belongs to the context's tenant.

CONSIDER logged as C6 gates: a denial and a recoverable tool error are both `is_error=True`, so the
loop must branch on `denied`; the registry hands out live `Tool` objects, so the choke point is
convention until the loop only sees `list()`; `_next_sequence` is not atomic; FR-070 must be
re-verified per real tool in C4 (the gateway cannot enforce scope, only pass it); `ToolError` and
validator messages must not interpolate secrets.

### Deviations
Checked against `STEP-C-SLICES.md` C3:
- `record_tool_call` moved from `app/harness/run.py` to `app/tools/gateway.py` (decision 4 above);
  the C2 test that imports it was updated. The `AgentToolCall` table itself is unchanged.
- No real tools yet — C4 adds the read-only repository tools.

### Blockers / Deferred
- **FR-067 `offset`/`limit`** is a per-tool obligation the ABC declares but does not enforce — C4.
- The remaining step-C gates: repository-read source (C4), `pydantic_ai` (C5), `skills-ref` (C7),
  frontend fixtures (C9).

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Backend suite, from the repository root: **458 passed**.
- No migration in this slice.

---

## Step C (FEASIBILITY §3) · Slice C4 — read-only repository tools

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. These
tools are the analyst's entire view of a customer repository, and a read tool that returns a secret
is a credential leak to the model.

**Status: COMPLETED** — fussion-reviewer **BLOCKED** on rounds 1 and 2 (credential reachability),
then **PASS WITH FINDINGS** on round 3; every finding fixed and re-verified. Committed with this
entry.

### Objective
FR-064, FR-067, FR-070: `read_tree`, `read_file`, `search_code` over a containment-checked
workspace — bounded output with an explicit truncation signal, model-readable errors, and scope
resolved from the `ExecutionContext`.

### Completed Work
- **`app/services/repository/reader.py`** — the `RepositoryReader` Protocol and DTOs, and
  `LocalWorkspaceReader`: containment-checked, denial-filtered, symlink-safe, and off the event
  loop (`asyncio.to_thread`).
- **`app/tools/repository.py`** — `ReadTreeTool`, `ReadFileTool`, `SearchCodeTool`; all read-only,
  capability `repository.read`; `offset`/`limit` and a `total` with `truncated`; reader resolved
  from the context via an injected resolver.
- **`ExecutionContext.workspace_reference`** — the opaque handle the future resolver resolves.
- **Tests** (`tests/test_repository_tools.py`, 16 + 2 skipped) — listing, paging, truncation,
  missing files, traversal, secrets/VCS paths (case, trailing-dot, short-name and linked-directory
  variants), symlink escapes, scope from the context, and a gateway round-trip.

### Architectural & Technology Decisions
1. **The read source is the local workspace clone (AGENT-ARCHITECTURE §7), not the network.**
   `GitProvider` was not extended: tree listing and code search are natural on a checkout, and the
   Phase 05 acquisition/workspace substrate already clones at a pinned SHA with path containment.
2. **Containment, then denial, then read.** `WorkspaceManager.assert_path_contained` rejects `../`,
   absolute and escaping-symlink paths; denial is then judged **on the resolved target** so a
   directory link into `.git` cannot smuggle a read.
3. **Secrecy is a first-class rule of the reader.** VCS metadata, dependencies, build output,
   `.env*`, credential/key files and every `protected_paths.protected_reason` path are never
   listed, read or searched. Matching is case-insensitive and trailing-dot/space normalised, because
   Windows folds both. The workspace's `.git/config` holds the clone token — this is the leak the
   reviews caught.
4. **Blocking filesystem work runs in a thread**, so a large search cannot stall the event loop.
5. **Bounded output with `offset` + `total` + `truncated`** (FR-067), so a large repository is
   pageable rather than permanently unreachable.

### Review history
Three rounds (Tier 1). Rounds 1 and 2 returned **BLOCKED**; round 3 passed.
1. **Round 1 BLOCKED — `read_file(".git/config")` returned the clone's GitHub token**, and `search`
   followed a committed symlink out of the workspace. Fixed: a denial layer in `_resolve`, and
   symlink skipping in listing and search.
2. **Round 2 BLOCKED — `.GIT/config` (case) and a `vendor -> .git` directory link both still
   reached the token.** Fixed: case/whitespace normalisation in `_is_denied`, and denial re-checked
   on the resolved path in `_resolve` and `_denied`.
3. **Round 3 PASS WITH FINDINGS** — regression cases added (`.git./config`, `GIT~1/config`,
   `.env.`, `credentials./token.json`) and the directory prune made case-insensitive so it agrees
   with `_is_denied`.

### Deviations
Checked against `STEP-C-SLICES.md` C4:
- The reader gained a denial layer the plan did not name, in direct response to the reviews. It is
  now the load-bearing part of the slice.
- No production resolver exists yet (nothing turns `workspace_reference` into a reader); C6/C10
  wire it. Tests inject one.

### Blockers / Deferred
- The two symlink tests **skip on Windows** (no symlink privilege); the code paths are covered on
  Linux CI and by the directory-junction test on Windows.
- `.env.example` is denied along with `.env` (CONSIDER) — safe direction; an allowlist is a later
  refinement.
- Remaining step-C gates: `pydantic_ai` (C5), `skills-ref` (C7), frontend fixtures (C9).

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Reader tests: **16 passed, 2 skipped**; full backend suite **474 passed, 2 skipped** at the
  round-2 fix point, and the reader tests re-run green after the round-3 touch-ups.
- No migration in this slice.

---

## Step C (FEASIBILITY §3) · Slice C5 — AgentRunner seam and Pydantic AI adapter

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. This
introduces the model path the analyst runs on.

**Status: COMPLETED** — fussion-reviewer PASS WITH FINDINGS, no BLOCKING finding; both SHOULD FIX
findings and the cheap CONSIDERs fixed and re-verified. Committed with this entry.

### Objective
ADR-001, FR-072, FR-125: adopt Pydantic AI behind Fussion's own `AgentRunner` Protocol, with
structured output validated, `pydantic_ai` imported only in `app/llm/adapters/`, and usage flowing
through the model gateway.

### Completed Work
- **`app/harness/runner.py`** — the `AgentRunner` Protocol, `AgentRunResult`, `StructuredOutputError`,
  `AgentRunnerError`, and the `UsageRecorder` seam.
- **`app/llm/adapters/pydantic_ai_runner.py`** — `PydanticAIAgentRunner` (the only module importing
  `pydantic_ai`), `_build_model`, and `gateway_usage_recorder`.
- **`app/llm/factory.py`** — `ProviderConfig` + `resolve_provider_config`, the single provider
  selector the text provider and the agent adapter both read.
- **`app/llm/gateway.py`** — `ensure_budget` (pre-call) and `record_external_usage` (post-call), so
  agent calls are metered in the same ledger as runtime calls.
- **Tests** (`tests/test_agent_runner.py`, 7) — structured output parsed, usage returned and
  recorded, unparseable output a failed step, text output when no schema, the framework confined to
  the adapter, a fake runner substituting, and the recorder writing through the gateway.

### Architectural & Technology Decisions
1. **The harness depends on `AgentRunner`; Pydantic AI is one implementation.** `app/agents/` and
   `app/harness/runner.py` never import the framework (verified by a repo-wide test).
2. **Unparseable output is a failed step, a provider failure is not.** `UnexpectedModelBehavior`
   maps to `StructuredOutputError`, but `ContentFilterError` and `IncompleteToolCall` — which
   subclass it — map to `AgentRunnerError`, so a content filter is not mislabelled as bad output.
3. **Usage flows through the gateway.** The adapter returns usage and hands it to a recorder; the
   harness wires `gateway_usage_recorder`, which writes to the same `ModelUsage` ledger via
   `record_external_usage`, and checks `ensure_budget` before the call.
4. **One provider selector.** `resolve_provider_config` is shared by the text provider and the agent
   adapter, so adding a vendor is one edit and the two cannot drift.
5. **No key, no call.** The adapter fails fast rather than attempting a call on an empty credential.

### Review history
One round (Tier 1 gate), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. FR-125 was
verified by grep. Two in-slice findings, fixed per §9.0:
1. **Usage did not actually flow through the gateway** — the adapter called the provider directly
   and the recorder was a bare callback with no gateway entry point. Added
   `ModelGateway.ensure_budget`/`record_external_usage` and `gateway_usage_recorder`, with a test
   that writes a `ModelUsage` row.
2. **Provider selection was duplicated** between the factory and the adapter. Extracted
   `resolve_provider_config` as the single selector.

CONSIDER fixed: the exception mapping narrowed (see decision 2); the adapter fails fast without a
key; the dependency floor tightened to `pydantic-ai>=2.43.0`. CONSIDER logged as C6/C8 gates: the
`context` parameter is a signature-only seam until tools need `deps_type`; `definition.tools` is
ignored until tool dispatch exists; `_build_model` is covered by inspection, not a test (all tests
inject a model).

### Deviations
Checked against `STEP-C-SLICES.md` C5:
- `app/llm/factory.py` and `app/llm/gateway.py` were extended beyond the slice's two new files, to
  satisfy "usage flows through the gateway" and remove the duplicated selector.
- `backend/tests/conftest.py` was briefly changed and reverted: a drop-before-create experiment
  caused cross-file setup errors; the stale database from the interrupted run was deleted instead.

### Blockers / Deferred
- **Tool dispatch** and **budget enforcement wiring** are C6; the **eval corpus** is C9.
- Remaining step-C gates: `skills-ref` (C7), frontend fixtures (C9).

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Backend suite, from the repository root: **481 passed, 2 skipped**.
- No migration in this slice. No test hits a paid API; pydantic_ai's `TestModel`/`FunctionModel` are
  used, and the fake runner substitutes.

---

## Step C (FEASIBILITY §3) · Slice C6 — the harness loop and budgets

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. The
loop is where tenancy, authorization, budget and audit meet the model.

**Status: COMPLETED** — fussion-reviewer **BLOCKED** on rounds 1 and 2, then **PASS WITH FINDINGS**
on round 3; every finding fixed and re-verified. Committed with this entry.

### Objective
FR-050, FR-053, FR-054: one harness loop that runs an agent through the framework, exposes its
declared tools through the gateway, enforces per-run budgets (tool calls, tokens, wall clock, cost),
and finishes the run record with a classified failure.

### Completed Work
- **`app/harness/budget.py`** — `BudgetTracker` and `RunBudgetExceeded`, enforcing all four ceilings.
- **`app/harness/loop.py`** — `run_agent`: build the run, bind the run id onto the context, check the
  organization budget, expose the agent's declared tools, run via `AgentRunner`, meter usage into
  the ledger, and finish `COMPLETED`/`FAILED` with a `FailureClass`.
- **`app/harness/runner.py`** — `HarnessError` base, `ToolDeniedError`, `AgentBudgetExceededError`,
  `ToolSpec`, `ToolExecutor`.
- **`app/llm/adapters/pydantic_ai_runner.py`** — builds pydantic_ai tools from Fussion schemas via
  `Tool.from_schema`, passes `UsageLimits`, and reports partial usage when the run fails.
- **Tests** (`tests/test_harness_loop.py` + the adapter test) — success, declared-tools-only, all
  four budget breaches, denial, structured-output, runner failure, and usage-on-failure.

### Architectural & Technology Decisions
1. **Pydantic AI owns the model loop; the harness owns the orchestration.** The loop is the
   framework's, behind `AgentRunner`; tenancy, authorization, budgets and the run record are the
   harness's — never the model's (FR-054).
2. **Harness errors survive the framework.** A policy denial or budget breach raised inside a tool
   is a `HarnessError`; the adapter re-raises it untouched, so a denial is recorded `REFUSED`, not
   rewritten into a provider failure.
3. **Usage is never lost.** The adapter accumulates usage as calls happen and reports it on failure;
   the harness writes the ledger before enforcing the budget and writes `tokens_used`/`cost_usd`
   onto the `AgentRun` on both success and failure.
4. **Every failure finishes the run.** Each classified branch, plus a catch-all, calls `_fail`; a
   run is never left `RUNNING` by a handled failure.
5. **The organization budget is checked before the call** (`ModelGateway.ensure_budget`), so an
   over-budget tenant cannot incur agent cost.

### Review history
Three rounds (Tier 1). Rounds 1 and 2 returned **BLOCKED**; round 3 passed.
1. **Round 1 BLOCKED** — `ToolDeniedError` was swallowed by the adapter's catch-all (denial
   misclassified as terminal), and usage was recorded only after a successful run, so failures lost
   it. Fixed with the `HarnessError` base and usage accumulation reported on failure.
2. **Round 2 BLOCKED** — usage reached the ledger but `AgentRun.tokens_used`/`cost_usd` stayed 0 for
   failed runs, and `prompt_hash`/`model_id` were success-only. Fixed: `_fail` writes the usage, and
   reproducibility is recorded before the run.
3. **Round 3 PASS WITH FINDINGS** — `ensure_budget` was never called (dead code) and cancellation
   lost usage. Fixed: the org budget is checked before the call, the adapter reports partial usage
   on cancellation, and the run id is bound onto the context so the gateway's ownership check is
   live.

### Deviations
Checked against `STEP-C-SLICES.md` C6:
- The slice named `loop.py` and `budget.py`; the adapter and runner gained the tool/error plumbing
  the loop needs.
- External cancellation (client disconnect, worker shutdown) still leaves a run `RUNNING`; there is
  no production caller yet, so it is logged as a gate on that caller.

### Blockers / Deferred
- **External cancellation / kill switch (FR-055)** — gate on a worker or request driving the loop.
- **`skill_versions`** is empty until C7 packages exist.
- The eval corpus (C9) is not applicable to this slice.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Backend suite, from the repository root: **493 passed, 2 skipped**.
- No migration in this slice.

---

## Step C (FEASIBILITY §3) · Slice C7 — skills structure and two packages

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. No
model call and no customer code; it is knowledge and its loader.

**Status: COMPLETED** — fussion-reviewer **BLOCKED** on round 1, then **PASS WITH FINDINGS** on round
2; every finding fixed. Committed with this entry.

### Objective
FR-078–083c: framework integration knowledge becomes versioned skill packages conforming to the
Agent Skills spec, loaded progressively, with a deterministic detection test and CI validation.

### Completed Work
- **`skills/integrations/nextjs-app-router/`** and **`skills/integrations/generic-html/`** — each with
  `SKILL.md` (frontmatter + instructions), `scripts/detect.py` (deterministic match), `assets/`
  (templates) and `references/EDGE-CASES.md`.
- **`app/skills/loader.py`** — `SkillLoader` with `index()` (metadata only), `get()` (body on
  demand), `read_asset`/`read_reference`, and `run_detection()`. `SkillMetadata` / `Skill` /
  `SkillNotFoundError` / `SkillFormatError`.
- **`app/core/config.py`** — `SKILLS_ROOT` override.
- **CI** (`.github/workflows/ci.yml`) — an `agentskills validate` step over every skill.
- **`pyproject.toml` / `uv.lock`** — `skills-ref` as a dev dependency.
- **Tests** (`tests/test_skills.py`, 13) — index vs body, on-demand assets/references, path
  traversal, protected paths, detection for both skills, spec validation, the token budget, and a
  missing-root failure.

### Architectural & Technology Decisions
1. **The spec is the format, not a private one.** Skills conform to agentskills.io, so models
   already interpret them and `agentskills validate` runs in CI (FR-083a/b).
2. **Progressive disclosure is real.** `index()` returns metadata only (the always-on ~100-token
   tier); `SKILL.md` loads on activation; templates and references load only when referenced (FR-081).
3. **Adding a framework is a new folder.** The loader discovers packages by directory, so no core
   edit is required (FR-079). The stored framework id becomes a skill id string (FR-082) when C10
   retires the `WebsiteFramework` enum.
4. **Detection is deterministic and self-contained.** Each skill ships `scripts/detect.py`; the
   loader runs it with a bounded timeout and a **scrubbed environment**, so a skill never sees the
   process's DB URL, JWT or API keys.
5. **The skills root fails loudly.** It resolves from `SKILLS_ROOT` (default repo-relative) and
   raises when absent, rather than reporting an empty catalogue.

### Review history
Two rounds (Tier 2). Round 1 **BLOCKED**; round 2 passed.
1. **Round 1 BLOCKED** — the CI step invoked `.venv/bin/skills-ref`, but the installed console
   script is `agentskills` (`skills-ref` is the package name), so the step exited 127 and never
   validated anything. Fixed; the validator now runs.
2. **Round 2 PASS WITH FINDINGS** — the docs still named `skills-ref validate` (fixed to
   `agentskills validate`), and the loader needed hardening (root resolution, subprocess timeout +
   scrubbed env, non-object detection output, `OSError`). All fixed.

### Deviations
Checked against `STEP-C-SLICES.md` C7:
- The slice named the two packages and the loader; CI, config and the dev dependency are the
  supporting wiring.
- **FR-082 is not closed here** — the stored framework id is still the `WebsiteFramework` DB enum;
  replacing it with a skill id is C10, as the slice plan states.
- The `assets/` templates are for step D (the CodingAgent). They are required by the skill layout
  (FR-083a) and are the skill's content, not speculative abstraction.

### Blockers / Deferred
- **`.j2` rendering**: no template engine is a dependency yet; step D adds one or the templates are
  consumed directly.
- **Two widget contracts** exist until step D/C10 retires `services/integration/artifacts.py`.
- Remaining step-C gates: frontend widget-target fixtures (C9).

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Skills tests: **13 passed**; the validator (`agentskills validate`) passes on both packages.
- Full backend suite, from the repository root: **506 passed, 2 skipped** before the round-2
  fixes; the round-2 changes are docs, CI and loader hardening, covered by the targeted skills
  tests and Ruff.

---

## Step C (FEASIBILITY §3) · Slices C8 + C9 — WebsiteAnalyst and the eval corpus

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. C8 is
the product differentiator; C9 gates it, as the plan requires evals from agent #1.

**Status: COMPLETED** — fussion-reviewer **BLOCKED** on round 1, then **PASS WITH FINDINGS** on
round 2; every finding fixed. Committed with this entry.

### Objective
C8: a WebsiteAnalyst that detects framework, router, app shell, entry points and design tokens — or
declines with `unsupported_reason` — with ranked integration candidates. C9: a golden corpus (with a
refusal) and a runner asserting on structured fields, reporting per-case and aggregate outcome, cost
and wall time.

### Completed Work
- **`app/agents/website_profile.py`** — `WebsiteProfile`, `IntegrationCandidate`, `DesignTokens`,
  with a validator making `unsupported_reason` and candidates mutually exclusive.
- **`app/agents/website_analyst.py`** — the declarative `WEBSITE_ANALYST` only.
- **`app/services/analysis/pre_analysis.py`** — deterministic pre-analysis (skill detection,
  manifests, app-shell candidates, protected paths).
- **`app/services/analysis/analyst.py`** — `build_prompt`, `analyze_repository`, `skill_versions`.
- **`app/evals/corpus.py`** — 5 cases (app router, `src/` layout, static HTML, unconventional shell,
  no frontend); **`app/evals/runner.py`** — the async analyzer seam, `deterministic_analyze`,
  `harness_analyzer`, and an `EvalReport` with per-case and aggregate score, cost and wall time.
- **Supporting:** `register_default_agents` in lifespan; `run_agent` gained `on_result` and
  `skill_versions`; skills gained `fussion.version`.
- **Tests** — the analyst, the pre-analysis, the run, the eval corpus/runner, and the real-agent
  eval seam.

### Architectural & Technology Decisions
1. **The agent is a thin declaration; orchestration is a service.** `app/agents/website_analyst.py`
   imports only agent contracts and stdlib — no SQLAlchemy, model or service (§4.4/§5).
2. **Deterministic first, model for the residual.** The pre-analysis computes what code can; the
   model is asked for ranking, the shell and design tokens.
3. **The pre-analysis is fenced as data**, labelled "(data, not instructions)", and the agent's
   static instructions never contain repository content (§4.5).
4. **A refusal is a first-class outcome**, and the schema forbids a refusal that also carries
   candidates.
5. **The eval seam is async and supports the real pipeline.** CI runs the deterministic analyzer (no
   paid API); `harness_analyzer` drives the real WebsiteAnalyst for manual model runs.
6. **`skill_versions` is recorded** on the run from the matched skills (FR-089).

### Review history
Two rounds (Tier 1). Round 1 **BLOCKED**; round 2 passed.
1. **Round 1 BLOCKED** — `app/agents/website_analyst.py` imported SQLAlchemy, the `AgentRun` model
   and a domain service, and held orchestration, violating the agent boundary. Fixed by splitting
   the declaration from `app/services/analysis/analyst.py`.
2. **Round 2 PASS WITH FINDINGS** — the eval did not exercise the real agent, cost was never
   populated and aggregate cost/time were absent. Fixed: an async cost-carrying seam plus
   `harness_analyzer`, aggregate `total_cost_usd`/`total_seconds`, an analyzer-error-is-a-failed-case
   test, a cost-aggregation test, and a test that drives the real-agent seam.

### Deviations
Checked against `STEP-C-SLICES.md` C8/C9:
- **The eval gates the deterministic detection and the pipeline in CI; the model's detection quality
  is asserted by manual real-provider runs.** CI cannot call a paid API, so this is the honest split
  the plan's Notes describe.
- **FR-089 tool versions are still unrecorded** (pre-existing from C2); logged below.

### Blockers / Deferred
- **Tool versions on `AgentRun` (FR-089)** — pre-existing; its own small change.
- **`harness_analyzer` has no CLI** — a manual model run currently requires a few lines of code.
- **FR-082** (skill id as the stored framework) and the control-plane wiring remain C10.
- The remaining step-C gate: none for C8/C9.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Backend suite, from the repository root: **522 passed, 2 skipped**.
- No migration in this slice.

---

## Step C (FEASIBILITY §3) · Slice C10 — control-plane wiring (backend)

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md` and unchanged. The
analyst becomes reachable from the product and its result is persisted.

**Status: COMPLETE (2026-09-13).** Delivered in two parts: the backend (this entry) and the
Studio surface + FR-082 (the next entry). The reviewer's first round was `PASS WITH FINDINGS` and
explicitly stated the backend alone did not meet the slice's done-when ("no framework dropdown, no
typed path"); the second part closes that finding. Committed with this entry.

### Objective
FR-082, FR-058–062, MVP acceptance #4: auto-detect the framework, shell and integration point and
persist the result keyed to a pinned commit.

### Completed Work
- **`app/models/website_analysis.py` + migration 0018** — one row per analysis, keyed to
  `commit_sha`, cascading from the integration.
- **`app/services/analysis/clone.py`** — shallow-clone the integration's repository at its default
  branch, resolve the commit SHA, sanitize git output.
- **`app/services/analysis/analysis_service.py`** — resolve the model gateway, clone, build the
  trusted context (workspace reference + commit), run the analyst through the harness with the
  repository tools bound to the workspace, persist the profile, and tear the workspace down.
- **`POST /website-integrations/analyze`** and **`GET /website-integrations/analysis`**, with
  tenancy via the existing dependency chain, `INTEGRATION_UPDATE`, an audit event, and error
  mapping (503 no model, 402 budget, 502 clone/analyst failure).
- **Tests** — the endpoint runs and persists, is tenant-scoped (404), and cascades on delete.

### Architectural & Technology Decisions
1. **The read substrate is now wired.** `workspace_reference` on the context finally has a
   production resolver: the workspace path a `LocalWorkspaceReader` reads. This is the C4 gate.
2. **The gateway is resolved before the clone**, so a no-model deployment fails without touching
   the repository.
3. **A failed run is committed, not rolled back.** `get_db` rolls back on a propagating exception,
   so the service commits the harness's FAILED `AgentRun` before re-raising (FR-089).
4. **Teardown reports its outcome.** `cleanup_workspace` returns whether the directory is gone and
   logs a survivor — a workspace holds a clone whose `.git/config` may embed a token.

### Review history
One round (Tier 1), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING finding. Five SHOULD FIX:
1. A failed run's record was lost to `get_db`'s rollback — fixed (decision 3).
2. Only `ModelNotConfiguredError` was mapped — the clone/analyst/budget failures now return legible
   502/402/503 instead of a generic 500.
3. Teardown was best-effort and silent — it now reports success and logs a survivor.
4. The tracker was not updated — this entry.
5. **FR-082 / the slice done-when is not met** — the analysis stores a `framework_skill_id` string,
   but `WebsiteIntegration.framework` is still the `WebsiteFramework` enum, and the create schema
   still accepts a framework and a typed `widget_target_path`. **Recorded as remaining, not done.**

CONSIDER logged: `/analyze` uses `INTEGRATION_UPDATE` where `POST /runs` uses `INTEGRATION_EXECUTE`
(same roles today); `GET /analysis` returns no staleness signal against current HEAD; the
`pydantic_ai`-isolation test matches substrings, so a dynamic import would evade it.

### Deviations
Checked against `STEP-C-SLICES.md` C10:
- **The slice is delivered in two parts.** This commit is the backend: detection runs and is
  persisted, and the endpoint is reachable. The **Studio surface** (removing the framework dropdown
  and the typed path, showing the detected profile) and **FR-082** (replacing the `WebsiteFramework`
  enum with a skill id string) are **not** in this change and remain the rest of C10.
- No customer code executes: the only subprocesses are `git clone` and the Fussion-authored
  `skills/.../scripts/detect.py`.

### Blockers / Deferred
- **Studio surface + FR-082 enum retirement** — the remainder of C10.
- **Feeding the analysis into the plan/generation path** — step D; today the analysis is served but
  the pipeline still uses the manually configured framework.
- **Tool versions on `AgentRun` (FR-089)** — pre-existing.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Migration 0018: `upgrade → downgrade → upgrade` verified on **both SQLite and a scratch Postgres
  database**.
- Backend suite, from the repository root: **525 passed, 2 skipped**.

## Step C (FEASIBILITY §3) · Slice C10 — Studio surface and FR-082 (part 2)

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), unchanged from part 1. This part retires the stored
framework enum and removes the last hand-configured inputs from the Studio.

**Status: COMPLETE.** This is the remainder the part-1 reviewer named as a SHOULD FIX and the
slice's done-when ("no framework dropdown, no typed path").

### Objective
FR-082: adding a framework is a new skill package, not an enum value and a migration. C10 done-when:
framework, shell and integration point are auto-detected and persisted; no framework dropdown, no
typed path.

### Completed Work
- **FR-082 — the enum is gone.** `WebsiteFramework` and the `website_framework` Postgres enum are
  removed. `WebsiteIntegration.framework_skill_id: str` (default `nextjs-app-router`) and
  `WebsiteAnalysis.framework_skill_id` are plain skill-id strings; `DEFAULT_FRAMEWORK_SKILL_ID`
  and `GENERIC_HTML_SKILL_ID` are the only constants. `planner.py`, `artifacts.py`, `validation.py`,
  `pipeline.py`, the schemas and the endpoint are keyed on the string.
- **Migration `0019_framework_skill_id`** — adds `framework_skill_id`, backfills
  (`GENERIC_HTML` → `generic-html`, everything else → the default), drops `framework` and, on
  Postgres, the enum type. The downgrade recreates the type explicitly before `ADD COLUMN`
  (Postgres does not create a type implicitly), then restores the enum column and backfills it.
- **`backend/scripts/seeds/0019_framework_skill_id.py`** — one row of each former enum member at
  revision 0018, so the backfill is exercised against pre-existing rows.
- **Studio surface** — the framework dropdown and the typed `widget_target_path` are removed from
  both the Studio stage (`WebsiteStageView`) and the integrations form (`RepositoryConnectionForm`).
  The connected panel shows the detected `framework_skill_id` and the top ranked candidate, and an
  **Analyze Repository** action (`POST /analyze`) renders the persisted profile: router, language,
  package manager, build command, ranked integration candidates, entry points, or the refusal
  (`unsupported_reason`).
- **API client** — `websiteIntegrationApi.analyze` / `getLatestAnalysis`, a `WebsiteAnalysis` type,
  and `WebsiteFramework` deleted from `lib/api/integration.ts` and the feature types.
- **Tests** — a frontend test asserts the dropdown and typed path are absent, and that the analysis
  panel renders the detected framework and integration point after the action runs.

### Architectural & Technology Decisions
1. **The stored identifier is a skill id string, not a database enum.** Adding a framework no longer
   means an enum value and a migration. Full skill-registry dispatch is not yet in place — the
   generator still branches on the id in `planner.py`, `artifacts.py` and `validation.py`, so adding
   a framework still edits those three. That is a gate on step D, not a claim this slice satisfies
   the OCP failure in CLAUDE.md §6.
2. **The Studio shows a ranked list, not a single guess.** The panel renders the analyst's ranked
   `integration_candidates`; the top candidate is displayed, the rest remain visible.
3. **The analysis drives the displayed framework and integration point.** The connected panel shows
   `analysis.framework_skill_id` and the top candidate, falling back to the persisted
   `config.framework_skill_id` / `widget_target_path` only before the analyst has run.
4. **An unknown skill id is refused at configuration time** (FR-082). The stored value is a free
   string, so the create/update schema rejects an id the generator cannot build and bounds its
   length, rather than letting it reach the planner and produce a plan with no files.

### Review history
One round (Tier 1), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING. SHOULD FIX, all fixed:
1. The connected panel showed `config.framework_skill_id`, never the analysis, so a `generic-html`
   repo still displayed `nextjs-app-router` — the panel now prefers `analysis.framework_skill_id`.
2. `framework_skill_id` was an unbounded string against a `String(100)` column, and an unknown id
   produced an empty plan — the schema now bounds the length and rejects unknown ids.
3. Framework knowledge is still `if framework_skill_id ==` branches in three core modules — recorded
   above as a step-D gate, not a defect this slice can close.
4. The frontend test was vacuous (config and analysis shared the same value) — the fixture now makes
   the analyst disagree with the config, so the assertion proves the analysis drives the display.
CONSIDER logged: the migration verifier checks schema/counts but not the backfill mapping; the
analysis is served but not yet fed into planning (step D).

### Deviations
- **The plan/generation path still reads `integration.framework_skill_id`.** Feeding the analysis
  into planning and generation is step D; C10's done-when is detection and persistence, which is met.
- **`widget_target_path` remains a column and is still defaulted** — it is no longer typed by a user;
  the displayed integration point prefers the analyst's top candidate.

### Blockers / Deferred
- **Feeding the analysis into the plan/generation path** — step D, as recorded in part 1.
- **Skill-registry dispatch instead of `if framework_skill_id ==`** — step D, so adding a framework
  is genuinely a new folder rather than edits to planner/artifacts/validation.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Migration 0019 with its seed: `upgrade → downgrade → upgrade` verified on **both SQLite and a
  scratch Postgres database**.
- Backend suite, from the repository root: **526 passed, 2 skipped**.
- Frontend, from `frontend/`: `pnpm build` clean; `pnpm test` — **109 passed** (9 files).

## Step C (FEASIBILITY §3) · Slice C11 — detection becomes the configuration

**Rigour tier: 1 — Maximum** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md`. This slice is the
critical path of `GAP-CLOSURE-PLAN.md`: it makes the C10 analyst's result drive the plan and the
pull request, so acceptance #4 ("automatically detected, without selecting") is true end to end.

**Status: COMPLETED** — the Tier-1 reviewer returned **PASS WITH FINDINGS**, no BLOCKING; all four
SHOULD FIX were reachable and are fixed. Committed with this entry.

### Objective
MVP acceptance #4 and #5: the detected framework and integration point become the integration's
configuration, an unanalysable repository refuses with its reason, and a model-authored target
cannot become a write target.

### Completed Work
- **`app/services/analysis/selection.py`** — `select_target(profile)` returns the chosen
  `(framework_skill_id, widget_target_path, confidence)` or declines: unsupported, no candidate
  above `TARGET_CONFIDENCE_THRESHOLD` (0.6), an unknown skill, or every candidate an unsafe path.
- **`app/core/target_paths.py`** — `unsafe_target_reason`, one gate for a typed path and an
  analyst-chosen one: repository-relative, no traversal, no control characters, within the
  `String(255)` column, and not a protected path.
- **`analysis_service.py`** — on success, the selection is written onto the integration; declining
  is non-destructive (an existing configuration is never clobbered by a below-threshold re-analysis).
- **Refusal** — `GET /plan` and `POST /runs` both refuse with the analysis's `unsupported_reason`
  (acceptance #10). The pipeline refuses before allocating a sandbox or recording a run.
- **Staleness** — `GET /plan` warns when the branch head differs from `analysis.commit_sha`; not a
  block.
- **Studio** — the ranked candidates each get a "Use this" action (a choice, not a typed path); the
  PATCH is validated by the same gate.
- **`app/services/analysis/queries.py`** — `get_latest_analysis`, shared by the control plane and
  the pipeline, so "latest analysis" is defined once.
- **Tests** — selection (unit), the path gate (parametrised), the analyze-commits /
  below-threshold / non-destructive-re-analysis / unsupported-refuses behaviour, and the frontend
  pick.

### Architectural & Technology Decisions
1. **Detection writes the existing columns.** `pipeline.py` was not changed — it already read
   `framework_skill_id` and `widget_target_path`. C11 makes the analyst their writer.
2. **One path gate, two callers.** The configuration schema and the analyst's selection apply the
   same `unsafe_target_reason`, so a path is safe however it was chosen. This closes the human-pick
   route the reviewer found open.
3. **Declining is not an error and is non-destructive.** A weak or refused analysis leaves the
   integration's configuration as it was; a human chooses in the Studio.
4. **The pipeline reads the latest analysis through a neutral query module**, not by importing the
   analyst stack, keeping the integration pipeline free of the LLM dependency.

### Review history
One round (Tier 1), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING. SHOULD FIX, all fixed:
1. The "Use this" route bypassed the traversal/absolute gate (PATCH only checked protected paths) —
   the schema now applies the full `unsafe_target_reason` gate.
2. No length bound on a model path → a Postgres `DataError` (500), invisible on SQLite — bounded at
   `MAX_WIDGET_TARGET_LENGTH` (255).
3. Null bytes and control characters passed — now refused.
4. The "leave unconfigured" comment was false for an already-configured integration — the behaviour
   is now explicitly non-destructive and covered by a re-analysis test.
CONSIDER logged: repository identity is not part of the analysis key (a repo change should
invalidate the analysis); the staleness warning is plan-only; the absence of an analysis does not
refuse (it fails later at "target not found").

### Deviations
- **Repository identity is not part of the analysis key** — the primary connect flow deletes and
  recreates the integration, so this is logged as a gate on the edit-repository flow, not fixed here.
- **The staleness signal is on `GET /plan` only** — a run carries no staleness warning yet.

### Blockers / Deferred
- **Repository-identity invalidation** and **run-time staleness** — small follow-ups on the
  edit-repository and run surfaces.
- **Skill-registry dispatch** — still step D, unchanged.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- No migration in this slice.
- Backend suite, from the repository root: **554 passed, 2 skipped**.
- Frontend, from `frontend/`: `pnpm build` clean; `pnpm test` — **109 passed** (9 files).

## Step C (FEASIBILITY §3) · Slice C12 — the run change set

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md`. Backend behaviour with
no customer-repo, credential or cross-tenant path: it records and serves what the run already
generated.

**Status: COMPLETED** — the reviewer returned **PASS WITH FINDINGS**, no BLOCKING or SHOULD FIX; the
CONSIDERs are logged and the one untested branch is now covered. Committed with this entry.

### Objective
Close `CLAUDE.md` §3.7: `GET /runs/{id}/diff` served a placeholder because file content was not
persisted, and before that it re-derived a diff the pull request never contained. Persist the change
set at generation time and serve it verbatim.

### Completed Work
- **`app/services/integration/changeset.py`** — `build_change_set` computes a per-file unified diff
  from the exact bytes the run wrote: created files against empty, modified files against the
  content that was read. Paths sorted, so the stored set is deterministic.
- **`IntegrationRun.change_set`** (JSON, nullable) + **migration `0020_run_change_set`** — nullable
  by design, so there is no backfill and no seed module. Reversible on both dialects.
- **`pipeline.py`** — the change set is recorded after generation and before validation, so a run
  that later fails still records what it had generated. It persists with the run on both the success
  and failure commit paths.
- **`GET /runs/{id}/diff`** — serves the stored set verbatim; a pre-C12 or refused run falls back to
  its recorded plan paths and a placeholder, and a run with no plan at all returns 409. It never
  re-derives content from the current configuration.
- **Tests** — the change-set unit tests, the happy-path diff (real content), the refused-run
  fallback, and the 409 branch.

### Architectural & Technology Decisions
1. **Compute once, at generation time, from the bytes written.** The stored after-side is the same
   dict `commit_files` receives, so the served diff cannot disagree with the pull request.
2. **Nullable, not backfilled.** An absent change set means "none" — refused before generating, or
   predates C12 — which is a real state, so no seed module is required.
3. **The change set is not in `IntegrationRunRead`.** List and detail responses do not carry customer
   file content; only the dedicated diff endpoint serves it.

### Review history
One round (Tier 2), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING or SHOULD FIX. CONSIDERs
logged: a create path that already exists at `base_sha` shows as a full add (an inherited
planner-classification limit, reachable only on a re-run against an already-integrated repo); a
failed run's diff describes generated-but-uncommitted content (intentional, disambiguated by
`status`/`error_message`); the pre-C12 fallback and 409 branches were untested (now covered).

### Deviations
- **None from the slice definition.** The fallback for pre-C12 runs is a small addition the slice
  plan implies (existing runs have no change set).

### Blockers / Deferred
- **Create-path fidelity on a re-run** — inherited from the planner's create/modify classification,
  not introduced here; a gate on the re-integration flow.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- Migration 0020: `upgrade → downgrade → upgrade` verified on **both SQLite and a scratch Postgres
  database**. No seed — the column is nullable with no backfill.
- Backend suite, from the repository root: **556 passed, 2 skipped**.
- Frontend, from `frontend/`: `pnpm build` clean; `pnpm test` — **109 passed** (9 files).

## Step C (FEASIBILITY §3) · Slice C13 — the Studio SSE session leak

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md`. A backend behaviour
change with no customer-repo or credential path; the one security-relevant surface is the stream's
authorization, which is unchanged in what it checks.

**Status: COMPLETED** — the reviewer returned **PASS WITH FINDINGS**, no BLOCKING; the one SHOULD FIX
(the session guarantee was untested) is fixed. Committed with this entry.

### Objective
Close `CLAUDE.md` §3.6: `studio_events.py` held an `AsyncSession` for the life of each connection
while polling every second, which would exhaust the pool.

### Completed Work
- **`app/api/deps.py`** — `authorize_project_stream`: resolves the user, tenant, permission and
  project in its own short-lived session and returns the trusted project id. It composes the
  existing resolution functions directly, so the checks are identical to a normal request.
- **`studio_events.py`** — the route no longer depends on `get_db` (which FastAPI closes only after
  the response completes); the generator opens a short-lived session per poll, serialises the frames
  inside that session, and closes it before yielding. The disconnect check and the wire format are
  unchanged.
- **Tests** — the authorization path (valid, cross-tenant 404, no credentials 401), a structural
  guard that the route's dependency tree contains no `get_db`, and a generator test asserting no
  session is open at any yield and that the poll loop opens its own session.

### Architectural & Technology Decisions
1. **A streaming route must not depend on a session-yielding dependency.** FastAPI closes a `yield`
   dependency only after the response completes, so the fix is not just the generator — the auth
   dependency itself has to release its session before the stream begins.
2. **Authorization is composed, not duplicated.** `authorize_project_stream` calls the same
   `get_current_user` / `get_current_organization` / `require_permission` / `get_current_project`
   functions a normal request uses, so there is one definition of each check.
3. **Frames are serialised inside the session.** The generator yields plain strings, so nothing is
   read from a detached ORM instance after its session closes.

### Review history
One round (Tier 2), fresh reviewer — **PASS WITH FINDINGS**, no BLOCKING. The reviewer confirmed
authorization equivalence (the explicit permission check is necessary, since `get_current_project`
does not enforce it) and that no pooled connection is held across a yield. SHOULD FIX: the session
guarantee was untested — now covered by the generator test. CONSIDER logged: the dependency uses
`get_session_factory()` directly, so a future `dependency_overrides[get_db]` would not apply to it;
the composition hand-mirrors the permission set.

### Deviations
- **None from the slice definition.**

### Blockers / Deferred
- **`dependency_overrides[get_db]` does not affect the stream auth path** — no override exists today;
  a gate on introducing one.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- No migration in this slice.
- Backend suite, from the repository root: **561 passed, 2 skipped**.
- Frontend: no change; last run `pnpm build` clean, `pnpm test` **109 passed**.

## Step C (FEASIBILITY §3) · Slice C14 — the sandbox contract

**Rigour tier: 2 — Standard** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md`. A naming and
contract change with no behaviour on any request path; the one live method added (`run`) refuses.

**Status: COMPLETED** — reviewer pending; see Verification for the run that was interrupted.

### Objective
`CLAUDE.md` §2/§3: the class named `SandboxManager` provides no process, filesystem or network
isolation — the name claims otherwise. Rename it to what it is, and define the `SandboxProvider`
Protocol a real backend must satisfy.

### Completed Work
- **`SandboxManager` → `LocalWorkspaceProvider`** (`app/services/integration/sandbox.py`): a
  path-checked per-run file workspace, not a sandbox. `pipeline.py` now holds `self.workspace`, and
  `services/integration/__init__.py` exports the new name.
- **`SandboxProvider` Protocol + `SandboxResult` + `SandboxNotSupportedError`**: the contract for a
  future container backend.
- **`LocalWorkspaceProvider.run()` refuses** with `SandboxNotSupportedError`, so nothing pretends to
  execute customer code on the control plane (`CLAUDE.md` §4.6).
- **Tests** — the workspace provider satisfies the Protocol shape; `run()` refuses.

### Architectural & Technology Decisions
1. **The name now matches the capability.** File containment is a workspace concern; isolation is a
   sandbox concern, and no sandbox exists.
2. **The Protocol is defined before the implementation is needed**, because a second implementation
   (the container) is now plausible — the condition `CLAUDE.md` §3 set for adding it.
3. **`AgentRun.skill_versions` needed no work here.** It was already populated from the matched skill
   packages when the analyst was built (C8), contrary to C6's "empty until C7" note.

### Deviations
- **The `AgentRun.skill_versions` half of the slice was already delivered** in C8; this slice is the
  sandbox contract alone. Recorded rather than re-implemented.

### Blockers / Deferred
- **A container-backed `SandboxProvider`** — post-MVP per `FEASIBILITY.md` §4; the Protocol is the
  seam.

### Verification (2026-09-13)
- Ruff, from `backend/`: `All checks passed!`
- No migration in this slice.
- **Full suite run interrupted by the operator.** The affected suites were run instead:
  `test_website_integrations.py` + `test_sandbox_provider.py` + `test_integration_safety.py` —
  **186 passed**. The full suite should be re-run before the next release.
- Frontend: no change.

## Step C (FEASIBILITY §3) · Slice C15 — project memory reconciled

**Rigour tier: 3 — Light** (CLAUDE.md §9.0), declared in `STEP-C-SLICES.md`. Documentation only.

**Status: COMPLETED.** The plan and the code now state one position on FR-058–062.

### Objective
C2/C6 notes said project memory "lands within C2/C6", but no memory model exists. Reconcile the
claim with reality rather than leaving a silent gap.

### Completed Work
- **`STEP-C-SLICES.md` Notes** — FR-058–062 is the persisted, `commit_sha`-keyed `WebsiteAnalysis`,
  not a separate tier. A durable memory tier is deliberately deferred under the Part D YAGNI
  register (working-memory compaction, cross-session memory) until a run demonstrates the need.
- **This entry** — the position is recorded where the step's status is read.

### Architectural & Technology Decisions
1. **The analysis is the MVP's project memory.** It is commit-keyed, tenant-scoped and staleness-
   aware, which is what the requirement needs at this scope.
2. **No durable memory tier is built.** Adding one now would be speculative; the trigger is a run
   that exceeds the context window despite bounded tool calls.

### Verification (2026-09-13)
- Documentation only: no code, no migration, no test change.
