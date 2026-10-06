# HANDOFF — Kali Setup & Continuation Notes

> **For the OpenCode (or human) session running inside Kali Linux.**
> This file was authored from a Windows session that cloned, analysed, and partially
> set up this repository. It records exactly what was done, what was found, what is
> already verified, and the precise remaining steps. Read it start-to-finish before
> doing anything, then continue from **§7 "Where we stopped / what remains"**.

---

## 0. TL;DR for the Kali agent

1. This is the repo `hecmatechnologies-eng/panthacloud-backend` (product name **Fussion**),
   a FastAPI backend. It is far more mature than its own README claims.
2. On Windows the app **already builds, boots, and passes 740/742 tests**. The 2 failures
   are Windows-only and will pass on Linux.
3. The remaining goal that was not finished: **run the full production-like stack on Linux**
   (native Docker → pgvector Postgres 17 + Redis 7 → all 30 migrations → 742/742 tests → boot).
4. Two real repo bugs were found and patched **only in the Windows clone**. The remote does
   **not** contain the fixes. Re-apply them on Kali (exact diffs in §5).
5. Follow §6 for the full bootstrap, then §8 for verification and the report format.

---

## 1. Repository facts (verified)

| Item | Value |
|---|---|
| Remote | `https://github.com/hecmatechnologies-eng/panthacloud-backend.git` |
| Default branch | `main` |
| HEAD at handoff | `ee1897ed797eca537e7231e19233be8ce1661018` (`ee1897e`) |
| Commits | 69, single author "Fussion Engineer", 2026-09-07 → 2026-09-19 |
| Language | Python (~1.6 MB), plus JS/HTML/Jinja templates |
| Python LOC (`backend/app`) | ~19,829 |
| Alembic migrations | 30 (latest `0030_knowledge_storage`) |
| API endpoint modules | 22 |
| Test files | 58 |
| Notebook-level dirs | `.github/`, `docs/`, `infrastructure/`, `backend/`, `skills/`, `.claude/` |
| `frontend/` | **does not exist in the repo** (README documents a Next.js Studio that is not committed) |

---

## 2. Maturity assessment (evidence-based — important context)

The README and `CLAUDE.md §2` ("honest current state") claim *"pre-MVP, not deployable, no LLM,
no live GitHub connection."* **This is stale.** The code and git history show a dense feature
burst **2026-09-12 → 2026-09-19** that the docs were never updated to reflect:

- `feat(runtime): tenant resolver, conversation store, public chat, model gateway, grounded retrieval (steps B2–B6)`
- `feat(agents): ExecutionContext, agent registry, and AgentRun persistence (step C2)`
- `feat(tools): tool contract, registry and gateway (step C3)`
- `feat(events): Redis Pub/Sub event streaming and ARQ async worker queue`
- `feat(core): Tier 0 stability and Tier 1 pgvector scaling`
- `feat(analysis): blobless clone, monorepo scanner, anti-hallucination gate`
- `feat(knowledge): Cloudflare R2 object storage and end-to-end vector pipeline`
- `feat(agent): autonomous coding agent, webhook origin auto-discovery, origin guardrails`
- `feat(security): Tier 3 distributed rate limiting, stateless JWT revocation`
- `fix(github): … GitHub App OAuth callbacks` (real GitHub App wiring, cross-subdomain)

Runtime startup log (observed) is the strongest evidence:
```
Starting Fussion Backend (fussion-backend) in development mode
Git provider: GitHubProvider (real repositories)
No model provider configured; public chat will return 503.
Embedding provider: gemini
Starting background workspace sweeper (interval: 900.0s)
```
So: a **real model plane** (`app/llm/` with Gemini + OpenAI-compatible providers, a
`pydantic_ai` runner, and a gateway), real agents/harness/tools, Redis pub/sub, ARQ workers,
pgvector migration, R2 storage, and a live GitHub provider all exist. `build_model_gateway()`
returns 503 only when no API key is configured — that is contract, not absence.

**Conclusion to carry forward:** the backend control + agent plane is substantially built and
appears deployable. Remaining genuine gaps: the `frontend/` is absent, the embedding provider
is still a deterministic-hash placeholder, and there are known hazards (see §9).

---

## 3. Environment / toolchain split (as established on Windows)

**System-wide (machine level):**
- `git` (2.54)
- `uv` 0.12.23 — the dependency/build tool
- *(Docker — see §4; not completed on Windows)*

**uv-managed (not global):**
- Python 3.13.16 (installed under the uv data dir, **not** a system Python)

**Project-scoped (inside `backend/.venv`, managed by uv):**
- Every dependency from `backend/pyproject.toml` (FastAPI, Uvicorn, SQLAlchemy, Alembic,
  pydantic/pydantic-settings, pyjwt, bcrypt, `pydantic-ai`, `google-genai`, `openai`,
  pgvector, redis, arq, boto3, …) plus dev extras (`pytest`, `pytest-asyncio`, `httpx`,
  `ruff`, `skills-ref`).

**Services (containers, not installed into the venv):** PostgreSQL 17 (+pgvector) and Redis 7.

> On Kali, replicate this split: uv + Docker system-wide; Python + all packages project-scoped
> in `backend/.venv`. Use `uv sync` (not global `pip`).

---

## 4. What was already done (Windows)

1. Cloned the repo to `C:\Users\Others\Desktop\panthacloud-backend`.
2. Installed `uv` and uv-managed Python 3.13.16.
3. Created `backend/.venv` and installed deps; **had to add `greenlet` manually** (see bug #1).
4. Copied `.env.example → .env` and `backend/.env.example → backend/.env`.
5. Ran the suite on the in-memory SQLite fallback:
   **`740 passed, 3 skipped, 2 failed`** in ~7m24s.
6. Booted the API (SQLite): `/health` and `/api/v1/health` → healthy, `/docs` → 200,
   **63 OpenAPI paths**.
7. Attempted Docker Desktop via winget → installer exited `0xFFFFFFFB` (UAC elevation
   declined at the time). WSL2 was not yet enabled. **Not resolved on Windows.**

**Not done (the remaining work):** the Linux full-stack run — native Docker, pgvector Postgres,
Redis, all 30 migrations, 742/742 tests, boot against the real datastores.

---

## 5. Two real repo bugs found (re-apply the fixes on Kali)

### Bug #1 — `greenlet` missing → every async test errors
`backend/pyproject.toml` declares `sqlalchemy>=2.0.30` **without the `[asyncio]` extra**.
A fresh `uv pip install -e ".[dev]"` omits `greenlet`, and importing
`sqlalchemy.ext.asyncio` raises:
> `The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed.`

**Fix (apply on Kali):**
```diff
--- a/backend/pyproject.toml
+++ b/backend/pyproject.toml
-    "sqlalchemy>=2.0.30",
+    "sqlalchemy[asyncio]>=2.0.30",
```
> Alternative that avoids the bug entirely: use `uv sync` — `uv.lock` already lists
> `greenlet`, so syncing from the lockfile installs it. The `pyproject.toml` fix is still
> correct and should be made.

### Bug #2 — compose Postgres image has no pgvector, but a migration needs it
Migration `backend/alembic/versions/0027_pgvector_knowledge_chunks.py` runs
```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector USING (embedding::text::vector);
```
but `infrastructure/docker-compose.yml` uses stock `postgres:17-alpine`, which **ships without
pgvector**, so `alembic upgrade head` fails at revision 0027.

**Fix (apply on Kali):**
```diff
--- a/infrastructure/docker-compose.yml
+++ b/infrastructure/docker-compose.yml
   postgres:
-    image: postgres:17-alpine
+    # pgvector-enabled image: migration 0027 runs CREATE EXTENSION vector, which the
+    # stock postgres:17-alpine image does not ship.
+    image: pgvector/pgvector:pg17
```

> Note: the local Windows clone already contains both fixes as **uncommitted** edits.
> If you mount the Windows partition you can also just copy the patched files.

---

## 6. Kali bootstrap (do this in order)

> Work inside ext4 (your Kali home). **Do not run the venv or Docker from a mounted NTFS/Windows
> path** — NTFS breaks exec bits, permissions, and symlinks for git repos and venvs.

```bash
# 1. Base tools
sudo apt update
sudo apt install -y git curl build-essential ca-certificates

# 2. uv (to ~/.local/bin)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"     # persist in ~/.bashrc
uv python install 3.13

# 3. Docker (native — no Docker Desktop)
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker                            # or log out/in

# 4. Clone into home
git clone https://github.com/hecmatechnologies-eng/panthacloud-backend.git ~/panthacloud-backend
cd ~/panthacloud-backend

# 5. Apply Bug #2 fix
sed -i 's#image: postgres:17-alpine#image: pgvector/pgvector:pg17#' infrastructure/docker-compose.yml

# 6. Env files
cp .env.example .env
cp backend/.env.example backend/.env

# 7. Deps — uv sync honors uv.lock (greenlet included). Also apply Bug #1 for correctness.
cd backend
sed -i 's#"sqlalchemy>=2.0.30"#"sqlalchemy[asyncio]>=2.0.30"#' pyproject.toml
uv sync --python 3.13
cd ..

# 8. Infra up (pgvector Postgres 17 + Redis 7)
docker compose -f infrastructure/docker-compose.yml up -d
docker compose -f infrastructure/docker-compose.yml ps    # wait until healthy

# 9. Migrations — all 30, including pgvector
cd backend
uv run alembic upgrade head
cd ..

# 10. Tests — expect 742/742 on Linux
cd backend
uv run pytest tests -q
cd ..

# 11. Boot
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 7. Where we stopped / what remains (continue here)

**Completed:** clone, toolchain, venv, env files, SQLite test run, SQLite boot verification,
and the two bug fixes.

**Remaining (the whole point of moving to Kali):**
- [ ] Apply Bug #1 and Bug #2 fixes (if not already present from the mount).
- [ ] Bring up **pgvector Postgres 17 + Redis 7** via the fixed compose file.
- [ ] Point `backend/.env` at Postgres:
      `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/fussion_db`
      (and, if Redis, `REDIS_URL` per `backend/.env.example`).
- [ ] Run `alembic upgrade head` and confirm **revision `0030_knowledge_storage`** is reached.
- [ ] Re-run the suite against Postgres; confirm **742 passed, 3 skipped, 0 failed**
      (the two Windows-only failures must disappear).
- [ ] Boot against the real stack; verify `/health`, `/api/v1/health`, `/docs`.
- [ ] Optionally set `MODEL_PROVIDER` + `MODEL_API_KEY` and `EMBEDDING_*` to exercise the
      model plane (otherwise public chat correctly returns 503).

---

## 8. Verification & expected results (report against these)

| Check | Command | Expected on Linux |
|---|---|---|
| WSL/loop hacks absent | `grep -rn WindowsSelectorEventLoopPolicy backend/app` | only guarded by `sys.platform == "win32"`, inert on Linux |
| Docker up | `docker compose -f infrastructure/docker-compose.yml ps` | postgres + redis `healthy` |
| pgvector present | `docker exec fussion-postgres psql -U postgres -d fussion_db -c '\dx'` | `vector` extension listed |
| Migrations | `uv run alembic current` | `0030_knowledge_storage (head)` |
| Tests | `uv run pytest tests -q` | **742 passed, 3 skipped** |
| Health | `curl -s localhost:8000/health` | `{"status":"healthy",...}` |
| OpenAPI | `curl -s localhost:8000/openapi.json \| python -c "import sys,json;print(len(json.load(sys.stdin)['paths']))"` | `63` |

If tests still show exactly 2 failures involving `git`/`subprocess`, the session is accidentally
still on a Windows-style event loop — verify you are running under Linux with `uvloop` active.

Please report back: migration head reached, exact pass/fail counts, health JSON, and the
pgvector `\dx` output.

---

## 9. Known hazards / caveats (from `CLAUDE.md §3` — do not "fix" blindly)

- **SSE leak:** `studio_events.py` holds an `AsyncSession` open per connection while polling
  every 1s; will exhaust the pool under load.
- **`GET /runs/{id}/diff` is deliberately broken** (raises 500). It must serve a persisted
  change set, not re-derive one. Leave it unless the task is specifically to fix it.
- **No real sandbox:** `SandboxManager` is a path-checked directory, not process/filesystem/
  network isolation. Nothing executes customer code yet.
- **Embeddings are a placeholder:** `DeterministicHashEmbeddingProvider` (lexical, not semantic).
- **Leaked dev secrets** were removed from source and git history (history rewritten
  2026-09-12); dev keys are now generated into a gitignored `.dev-secrets.json`.
- **`frontend/` is absent** from the repo; do not expect a Studio UI to build.
- **Do not extend retired layers** (contracts / integration-plan / adapter / execution-plan,
  migrations 0007–0008) — they are being retired in step C1.
- The repo's `README.md` and `CLAUDE.md §2` **understate** implemented features; trust the code
  and commit history over those sections.

---

## 10. Notes for the Kali OpenCode session

- Read `CLAUDE.md` before touching code — it is the project's engineering contract.
- Prefer `uv` for everything (`uv run`, `uv sync`); never `pip install` globally.
- Keep the changes from this handoff **local/uncommitted** unless the user explicitly asks to
  commit or push. This is a clone of someone else's public repository.
- The user's goal is to (a) run the full stack on Linux and (b) determine how mature the
  project is. Use §2 and §8 as the basis; push beyond them with fresh evidence.
