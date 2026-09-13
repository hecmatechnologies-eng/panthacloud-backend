# Gap-closure plan — the path from step C to a demonstrable MVP

This plan closes the gaps between the written MVP (`docs/requirements/MVP-REQUIREMENTS-V2.md`,
Part C) and the code as it stands after C10. It introduces **no new numbering scheme**: every unit
of work is an existing step-B slice (B7, B8) or a new step-C slice (C11–C15), defined in
`STEP-B-SLICES.md` and `STEP-C-SLICES.md`. Those slice tables remain the definition of each slice;
this document is only the sequencing, the dependency order and the acceptance mapping.

The governing rules are the repository's own (`CLAUDE.md`): reuse the seams that already exist,
deterministic first, a human in the loop, fail loud, no new infrastructure, one slice per session
with a declared rigour tier and a tracker entry in the same commit.

## What "gap" means here

Two different things are commonly called "deferred". They are treated differently:

- **YAGNI deferrals** — have an explicit trigger in the Part D register or `FEASIBILITY.md` §6, and
  do not block a Part C acceptance criterion. They stay deferred. Examples: the container sandbox,
  pgvector, OpenTelemetry, Temporal, multi-provider routing, MCP, durable memory tiers.
- **Gaps** — a Part C acceptance criterion requires the behaviour and nothing in the plan says the
  MVP can ship without it. These are the subject of this plan.

## Dependency order

```
C10 (done)
  └─ Phase 1: C11 ──────────────┐  critical path (acceptance #4, #5)
                                 │
Phase 2: C12, C13 ───────────────┤  independent of C11
Phase 3: C14, C15 ───────────────┘  independent
Phase 4: B7 ──> B8                    acceptance #8 (stream, then widget)
Phase 5: acceptance sweep             all 14 criteria
```

C11 is the critical path. C12–C15 are independent of it and of each other. B7 must precede B8 so
the widget is built once, against the streamed contract. Step D (agent-authored coding with a
build check) remains post-MVP per `FEASIBILITY.md` §4.

## Phase 1 — Detection becomes the configuration

### C11 — commit the detected profile onto the integration. Tier 1.

The analyst returns a ranked `integration_candidates` list and an `unsupported_reason`; nothing
consumes them, so the pipeline still plans and patches from the server-defaulted
`framework_skill_id` and `widget_target_path`. C11 makes detection the source of the integration's
configuration. **`pipeline.py` needs no change — it already reads both columns.**

Work:

- A small pure decision function (`app/services/analysis/select_target.py`): given a `WebsiteProfile`,
  return the chosen `(skill_id, path)` or a refusal, using a confidence threshold constant. Unit
  tested in isolation.
- A path gate for the **model-authored** candidate, which is untrusted input (invariant §4.5):
  reuse `_reject_protected_target` and reject absolute paths, `..`, and anything not repo-relative.
- The analyze endpoint writes the selection onto `WebsiteIntegration`.
- **Refusal is enforced**: when the latest analysis carries `unsupported_reason`, `GET /plan` and
  `POST /runs` refuse with that reason (acceptance #10). Today nothing checks it.
- **Human in the loop**: below the threshold, do not auto-commit; the Studio lists the ranked
  candidates and a "Use this" action selects one through the existing `PATCH`. Selecting a detected
  candidate is not "typing a path" (acceptance #4).
- **Staleness is a warning, not a block**: `GET /plan` already resolves the branch head; if it
  differs from `analysis.commit_sha`, add a plan warning.

Exit: a `generic-html` repository is detected, committed, and planned/patched as
`generic-html`/`index.html`; an unsupported repository refuses with its reason; a model path that is
protected or escapes the repository is refused. **Acceptance #4 and #5 true.**

## Phase 2 — Run and Studio truth

### C12 — persist the run change set. Tier 2.

Migration adds `change_set` to `integration_runs`. If it is `NOT NULL` with a default it alters
existing rows, so a `scripts/seeds/` module and `upgrade → downgrade → upgrade` on SQLite and a
scratch Postgres are required. The pipeline already holds `generated_files` and the plan at
generation time; store `{path, action, diff}` there. `GET /runs/{id}/diff` serves the stored set and
never re-derives it (`CLAUDE.md` §3.7).

### C13 — fix the Studio SSE session leak. Tier 2.

`studio_events.py` acquires a short-lived session per poll instead of one for the connection's
lifetime, with heartbeat and disconnect handling (`CLAUDE.md` §3.6). Done before Phase 4 raises SSE
volume.

Exit: **acceptance #9 true**; §3.6 and §3.7 closed.

## Phase 3 — Contract closeout

### C14 — `SandboxProvider` Protocol, workspace rename, `AgentRun.skill_versions`. Tier 2.

Rename `SandboxManager` → `LocalWorkspaceProvider` and define `SandboxProvider` with `run()` raising
(the second implementation is now plausible, so the Protocol is no longer speculative —
`CLAUDE.md` §3). Populate `skill_versions` on `AgentRun` now that C7 packages exist (FR-089).

### C15 — reconcile FR-058–062. Tier 3 (docs only).

State one position: the commit-keyed `WebsiteAnalysis` is the analyst's project memory at MVP;
richer tiers are step D with a trigger. Update `STEP-C-SLICES.md` Notes and the tracker so the plan
and reality agree.

## Phase 4 — The live demo

### B7 — SSE streaming on the public chat. Tier 2.

Add `POST /chat/stream` (`text/event-stream`) beside the existing JSON `/chat`, so the tested
contract is unchanged. Resolve tenant → retrieve → assemble → stream tokens; the final event carries
citations and usage; the visitor message is persisted before streaming and the assistant message
after; **no DB session is held across the stream**. Reuse `ModelGateway`. Keepalive and reconnection
are part of the slice's done-when.

### B8 — real Shadow-DOM widget and customer-origin CORS. Tier 1.

The widget source lives with the skill assets, independent of `artifacts.py` (per the B7/B8 note),
reads the public key, consumes the B7 stream and renders in a shadow root. Replace the global
`CORSMiddleware` for the public route with the integration's registered origins (invariant §4.11;
`allow_origins=["*"]` is never used in production). FR-097 scanning applies to the emitted widget.

Exit: **acceptance #8 true end to end on a real site.**

## Phase 5 — Acceptance and hardening

Map every Part C acceptance criterion to a named test or eval; anything unmapped is a gap, not a
deferral. Grow the eval corpus (FR-084) from real failures, keeping the refusal case. Re-check that
each YAGNI deferral still has a valid trigger and is not silently blocking a criterion.

## Acceptance mapping

| # | Criterion | Closed by |
|---|---|---|
| 1 | Account, organization and project | existing |
| 2 | Upload documents, indexed with citations | B6 (done) |
| 3 | Connect a GitHub repository | C10 (done) |
| 4 | Automatically detected framework, shell, integration point — no dropdown, no typed path | C10 + **C11** |
| 5 | Review a plan naming created and modified files | C10 + **C11** |
| 6 | Approve and receive a PR that preserves existing content | existing |
| 7 | Merge and deploy | existing |
| 8 | Open the widget on a live site and get a streamed, grounded, tenant-attributed, cited answer | **B7 + B8** |
| 9 | See the run's activity, cost and outcome in the Studio | **C12 + C13** |
| 10 | An unanalysable repository is refused with an explanation | **C11** |
| 11 | A failed integration still returns analysis plus manual instructions | existing (verify in Phase 5) |
| 12 | Evaluation runs green across the golden corpus | C9 (done) |
| 13 | No cross-tenant access from a public client key | B2/B4 (done) |
| 14 | Generated code passes the security scan | FR-097 (done) |

## Gates and non-goals

Every slice ends with: ruff, the full backend suite, `pnpm build` and `pnpm test`, migration
verification where it adds one, and a tracker entry in the same commit. **Tier 1 slices (C11, B8)
additionally require a `fussion-reviewer` round and iterate until no finding describes a defect
reachable by the code as it runs** (`CLAUDE.md` §9.0).

Explicitly **not** built: container sandbox / build validation, pgvector, OpenTelemetry, anomaly
detection, Temporal, multi-provider routing, MCP, full design-system inference, durable memory
tiers, a third agent.

## Critical path to a sellable demo

C11 → C12 → C13 → B7 → B8. C14 and C15 slot in wherever convenient.
