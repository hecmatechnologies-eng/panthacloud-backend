# Fussion — Development Workflow with AI Coding Agents

How to work on this repository with Claude Code (or any AI coding agent) without
reproducing the failure this codebase already survived once.

Companion to `CLAUDE.md` and `docs/FEASIBILITY.md`.

---

## 0. The honest framing

"Vibe coding" — describing an outcome and accepting whatever the model produces — is what
built the current state of this repository. Phases 01–11 landed in about two days, every
one recorded as *COMPLETED · Deviations: None · Blockers: None*, and the result included a
defect that overwrites customer files and a five-migration subsystem nothing references.

None of that happened because the model was bad. It happened because **nothing checked the
output against a standard.**

The practice that works is not slower. It has the same generation speed and a real
verification step. The whole of this document is that one idea, made concrete.

---

## 1. The loop

```
PLAN  →  IMPLEMENT  →  REVIEW  →  VERIFY  →  COMMIT  →  CLEAR
```

**Plan** — Use plan mode (`Shift+Tab` twice) for anything beyond a one-file change. Read
the plan properly before approving it. A plan naming files you did not expect is the
cheapest bug report you will ever get.

**Implement** — One step from `FEASIBILITY.md` §3 at a time. Not "do step B", but the
specific slice: *"add the public key and allowed-origin models plus the migration"*.

**Review** — `/agents` → `fussion-reviewer`, or ask for it by name. It reads `CLAUDE.md`
and the architecture docs cold and audits the diff. **Non-negotiable before anything is
called done.**

**Verify** — Ruff, pytest, `pnpm build`, `pnpm test`. Once evals exist, the eval suite too.
Running tests is not the same as reviewing; you need both.

**Commit** — Small, one concern, message explaining *why*.

**Clear** — `/clear` between slices. A session that has been running for three hours
carries stale assumptions from work already committed.

---

## 2. Context hygiene

The agent's context is a resource with a cost. Treat it like one.

- **One slice per session.** Don't let a session span step B and step C.
- **`/clear` after each commit**, not when the context is full. Clearing while things are
  going well is the habit; clearing when confused is too late.
- **Point at documents, don't paste them.** `CLAUDE.md` loads automatically. Say "per
  AGENT-ARCHITECTURE §4" rather than pasting the section.
- **Use subagents for wide reads.** "Which modules reference `RepositorySnapshot`?" is an
  Explore task; it burns the subagent's context, not yours.
- **Keep `CLAUDE.md` short enough to stay true.** It is read every session. If it grows to
  where nobody verifies it, it becomes decoration.

---

## 3. Prompt patterns that work on this repository

**Start of a slice**

> Read CLAUDE.md and docs/FEASIBILITY.md. We are on step B. This slice only: add the
> WebsiteIntegration public key, AllowedOrigin model, and the Alembic migration. No
> resolver, no runtime endpoint yet. Plan first.

**Before calling anything done**

> Run fussion-reviewer on this diff. Then run ruff and pytest. Report what failed; do not
> fix anything until I have read the findings.

**When the model proposes an abstraction**

> Which requirement in MVP-REQUIREMENTS-V2 needs this, and what is the trigger in the
> Part D YAGNI register? If neither, cut it.

**When touching the framework branches**

> This must not add another `if framework ==` branch. Per AGENT-ARCHITECTURE §6 that
> belongs in a skill package. Show me the skill-based approach before writing code.

**Finishing a phase**

> Update ANTIGRAVITY-PHASE-TRACKER.md. Under Deviations, record what you actually checked
> to conclude there were none. "None" without evidence is not acceptable.

---

## 4. Anti-patterns — each of these already happened here

| Anti-pattern | What it produced |
|---|---|
| "Build phases 5 through 8" | Five migrations and most of the test suite for a subsystem nothing uses |
| Marking complete without review | Phase 11's overwrite defect, shipped, with the PR announcing *"Sandbox validation: PASSED"* |
| "Deviations: None" as a default | Eleven phases with no recorded deviation and two serious ones present |
| Letting docs drift from code | README frozen at "Phase 01 Complete" through eleven phases |
| Accepting an abstraction because it sounds professional | `Task` proposed alongside `IntegrationRun`, which already existed |
| Trusting green tests as correctness | 81 passing tests; the overwrite bug passes all of them |

That last one is worth sitting with. The static validator checks for markers; the stub
contains markers; the tests check the validator. **Tests confirm the code does what it was
written to do, not that it should do that.** That is what review is for.

---

## 5. When to stop and think rather than prompt again

- The same fix has failed twice → the problem is upstream of what you're editing
- The agent proposes touching a subsystem you didn't mention → the boundary is wrong, or
  the request was
- A diff is much larger than expected → scope crept mid-implementation
- You're about to approve a plan you haven't fully read → stop; that is where defects
  enter

---

## 6. Git discipline

- **Branch per slice**, merged after review passes.
- **Small commits.** A commit touching migrations, endpoints, services and frontend is
  four commits.
- **Never commit `.env`, `*.db`, or `backend/data/workspaces/`.** Check the last one —
  there are roughly 2,000 leftover UUID directories and `data/` is not in `.gitignore`.
- **The tracker updates in the same commit as the work**, never in a tidy-up pass later.

---

## 7. Definition of a good session

You can answer all of these afterwards:

1. What slice did I finish?
2. What did the reviewer find, and what did I do about each finding?
3. What did I decide not to build, and why?
4. Is the tracker true?
5. Could someone else pick this up from the repository alone?

If any answer is "I'm not sure", the session isn't finished — regardless of whether the
code works.
