# Claude Code Setup for Fussion

Plugin assessment, MCP servers, and copy-paste `.claude/` assets.

Every plugin below was verified against its source. Claims made by plugin marketing are
reported separately from what independent testing found.

---

## 1. Plugin assessment

| Plugin | What it does | Verdict for Fussion |
|---|---|---|
| **claude-code-setup** | Official Anthropic. Scans a codebase and recommends hooks, skills, MCP servers, subagents. Read-only. | **Optional.** Safe, but this repo already has a hand-tuned `CLAUDE.md` and reviewer. Useful mainly for hook suggestions. |
| **ponytail** | A "strict simplicity ladder" pushing toward minimal code. | **Recommended.** Directly reinforces YAGNI and Optimize-for-Deletion — the exact discipline this codebase lacked when Phases 05–08 were built. |
| **task-observer** | Logs your corrections and recurring patterns, turns them into skill improvements. | **Recommended.** Your failure mode is repeated mistakes going uncaptured. Also mirrors the architecture's own principle: failures become Skills. |
| **headroom** | Compresses tool output before it reaches the model. | **Conditional.** Marketing claims 60–95% savings; independent testing finds **15–25%** on typical workloads. Useful during exploration. **Turn it off during implementation** — lossy compression of file contents is a poor trade in a repo whose worst bug was not reading a file properly. |
| **graphify** | Builds a knowledge graph of the codebase so the agent queries structure instead of reading files. | **Not yet.** Value scales with codebase size; yours is moderate (~40 backend modules). Adds an index that can go stale. Revisit if context pressure becomes real. Claimed "49x–70x" savings are marketing. |
| **claude-mem** | Captures each session into a local SQLite store and re-injects relevant context later. | **Skip for now.** `CLAUDE.md` plus git history is *curated* memory; claude-mem is *automatic* memory. Given that this project's failure mode is unverified conclusions being treated as fact, auto-re-injecting "we completed phase X" across sessions carries real risk. Ironically this is the same tiering argument as `AGENT-ARCHITECTURE.md` §4 — curated beats automatic. Revisit if re-explaining context becomes a genuine cost. |
| **omniroute** | Routes requests to free third-party models when you hit rate limits. | **Do not use on this repository.** Two reasons, both serious. (1) It routes your source through 290+ third-party providers on free tiers whose retention and training policies you have not reviewed — this is a company codebase that will hold customer repository access. (2) It has documented security vulnerabilities unless `JWT_SECRET`, `API_KEY_SECRET` and `STORAGE_ENCRYPTION_KEY` are changed from defaults. The "1.6 billion free tokens" figure is a theoretical ceiling across the whole catalogue, not a balance. Fine for throwaway experiments; not for Fussion. |
| **Agent Skills** | Not a plugin — an **open specification** for packaging procedural knowledge an agent loads on demand. Spec at agentskills.io/specification; reference skills at github.com/anthropics/skills; validation via the `agentskills` console script of the `skills-ref` package. | **The most important item on this page for Fussion.** Your entire framework-knowledge strategy (`AGENT-ARCHITECTURE.md` §6) is built on this mechanism. Two consequences: (1) **conform to the spec** rather than inventing a private format — see FR-083a–c; (2) browse `anthropics/skills` for well-written examples before authoring `nextjs-app-router`. Skill quality determines integration quality more than model choice does. |

### Install order

```bash
# Official marketplace
/plugin marketplace add anthropics/claude-plugins-official

# Recommended
/plugin marketplace add DietrichGebert/ponytail
# task-observer: place the skill folder at .claude/skills/task-observer/

# Conditional — exploration only, disable before implementation work
pip install "headroom-ai[all]"
```

---

## 2. MCP servers worth adding

| Server | Why, for this project |
|---|---|
| **Context7** (or equivalent docs MCP) | **Highest value.** You are adopting Pydantic AI, which is newer than most model training data. Up-to-date docs for Pydantic AI, SQLAlchemy 2.0 async and FastAPI prevents a whole class of confidently-wrong API usage. |
| **PostgreSQL MCP** | Inspect the dev database directly instead of round-tripping through the app. Useful constantly during steps B and C. Point it at the dev database only. |
| **GitHub MCP** | Your own PR and issue workflow. Also lets you evaluate it as a replacement for hand-rolled `github.py` (ADR-001 notes this as a later convenience swap). |
| **Playwright** | Step B: test the widget on a real page — Shadow DOM isolation, CSP behaviour, streaming. Hard to verify any other way. |

Skip anything that needs production credentials. Nothing in your MCP config should be
able to reach a customer's repository.

---

## 3. `.claude/settings.json`

The device bridge cannot write to `.claude/`, so create these by hand.

```json
{
  "permissions": {
    "allow": [
      "Bash(cd backend && .venv/Scripts/ruff check app tests)",
      "Bash(cd backend && .venv/Scripts/pytest tests*)",
      "Bash(cd backend && alembic *)",
      "Bash(cd frontend && pnpm test*)",
      "Bash(cd frontend && pnpm build)",
      "Bash(git status*)",
      "Bash(git diff*)",
      "Bash(git log*)"
    ],
    "deny": [
      "Bash(git push --force*)",
      "Bash(rm -rf*)",
      "Read(./backend/.env)",
      "Read(./frontend/.env.local)",
      "Read(./.env)",
      "Read(./backend/.dev-secrets.json)",
      "Read(./.dev-secrets.json)"
    ]
  }
}
```

These `deny` entries matter more than they look. The live key protecting stored GitHub tokens is
whatever `SECRET_ENCRYPTION_KEY` is set to, and in development that is the generated
`backend/.dev-secrets.json` (`app/core/dev_secrets.py`) — so it belongs on this list alongside the
`.env` files. Nothing should pull any of them into a context window. Note there is no checked-in
`.claude/settings.json` in this repository yet, so these are instructions, not an enforced policy.

---

## 4. Slash commands

Create these under `.claude/commands/`.

**`.claude/commands/slice.md`**

```markdown
---
description: Start a scoped implementation slice
---
Read CLAUDE.md and docs/FEASIBILITY.md.

Slice: $ARGUMENTS

Rules for this slice:
- Implement ONLY what is named above. Nothing adjacent, nothing anticipatory.
- Plan first and wait for approval.
- No new `if framework ==` branch anywhere in core code.
- Any new abstraction must cite a requirement ID or a YAGNI-register trigger.
- Stop and ask if this requires touching a subsystem I did not name.
```

**`.claude/commands/done.md`**

```markdown
---
description: Verification gate before calling work complete
---
Do not fix anything until I have read the results.

1. Run the fussion-reviewer subagent on the current diff.
2. cd backend && .venv/Scripts/ruff check app tests
3. cd backend && .venv/Scripts/pytest tests
4. cd frontend && pnpm test && pnpm build
5. If evals exist, run the eval suite.

Report: reviewer verdict and every finding, then each command's result.
Then list which conditional blocks of CLAUDE.md §9 apply to this change and
whether each item is met.
```

**`.claude/commands/tracker.md`**

```markdown
---
description: Update the phase tracker honestly
---
Update docs/antigravity/ANTIGRAVITY-PHASE-TRACKER.md for the work just completed.

Requirements:
- Status reflects what actually shipped, not what was attempted.
- Under Deviations, record what you CHECKED in order to conclude there were none.
  "None" with no evidence is not acceptable — this tracker has been wrong before.
- Under Blockers, include anything deferred and why.
- Do not mark COMPLETED unless fussion-reviewer passed.
```

---

## 5. Subagents

`fussion-reviewer` — already written; place at `.claude/agents/fussion-reviewer.md`.

Add **`eval-runner`** once the corpus exists (step C), not before. Two subagents is the
right number for this repo, for the same reason two product agents is: every additional
one adds a handoff and a maintenance surface.

---

## 6. What actually moves the needle

Ranked honestly, most to least impact:

1. **`fussion-reviewer` used every time.** Nothing else on this page comes close.
2. **A docs MCP for Pydantic AI.** Prevents confidently-wrong API usage on a library the
   model has thin training coverage of.
3. **`/clear` between slices.** Free, and it prevents the stale-assumption failures that
   produce orphaned subsystems.
4. **ponytail and task-observer.** Small, aligned, low risk.
5. Everything else is optimization around the edges.

The plugins are worth an hour of setup. They are not worth an afternoon — the review gate
and the eval corpus are where the actual leverage is.
