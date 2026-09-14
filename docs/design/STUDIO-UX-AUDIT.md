# Fussion Studio — UX Audit & Redesign Plan

**Date:** 2026-09-14 · **Author:** UX audit (design-led) · **Status:** approved direction — decisions in §14 taken; ready to execute Step F in slices
**Audited against:** working tree (uncommitted redesign in progress), backend as-built, `STUDIO-PRINCIPLES.md`, `STUDIO-IA.md`
**Rigour tier:** 3 (docs only). No code changed by this document.

---

## 0. Executive summary

The Studio is **mid-flight between two designs**: the old tab-based UI is deleted from disk,
the new "agent topology" IA is half-mounted, and the result is a product that is visually
ambitious but **functionally incoherent at exactly the moments that matter most**.

Three structural findings dominate everything else:

1. **The backend is far ahead of the UI — and the UI doesn't know it.** The contract docs
   still say "no LLM, no agents, no runtime plane." In fact the LLM gateway, the
   `WebsiteAnalyst` agent, the public chat runtime with visitor sessions, usage/budget
   accounting, and the GitHub App flow all exist and are wired. The Studio exposes almost
   none of this: you cannot test-chat with the assistant you're building (the endpoint
   exists), you cannot see visitor conversations (the tables exist), you cannot see what a
   run cost until long after (the ledger exists). **The single highest-leverage redesign
   move is surfacing what is already built.**

2. **The product's money moment — plan → approve → run → PR — is the weakest surface in
   the app.** It is currently a dry file list, a `ConfirmDialog`, a polling spinner, and a
   silently-swallowed diff fetch. Every reference product (GitHub, Cursor, Vercel, Devin)
   treats this class of moment as *the* designed surface: a review, an approval gate, a
   legible progress narrative, and a recoverable failure. Fussion's trust model
   (human-in-the-loop by default, P4) is architecturally correct and experientially
   absent.

3. **Two hero metaphors are fighting, and the wrong one is winning.** `STUDIO-PRINCIPLES.md`
   §5 names the **Integration Workbench** (Repository → Analysis → Plan → Change Set →
   Validation → PR) as the hero. `STUDIO-IA.md` makes the **brain-topology graph** the
   hero. The tree implemented the graph. But a fixed star topology with 8 static
   satellites is a *list wearing a graph costume* — and two of its nodes (Memory, and
   Skill before detection) are decorative, violating the IA doc's own honesty rule. The
   graph is a good *ambient status layer*; the pipeline is the product. The redesign puts
   the pipeline back on top and demotes the graph to where it is truthful.

Everything else — dead controls, dishonest previews, lost state on refresh, gated stages
you can click into and bounce off, 16 unused components, an unmounted toast system, a
hardcoded human being's name in the account menu — is real but fixable in slices.

**Recommendation:** proceed to redesign, framed as **Step F** in the repo's step/slice
discipline, sliced F0–F7 (§11), sequenced so the truthfulness fixes and the money-moment
rebuild land before any new surface is added.

---

## 1. Method and sources

**Artifact audit.** Every route, component, context, hook and API call in `frontend/src`;
every router, service, model and SSE event in `backend/app`. File:line citations for every
defect claim.

**Heuristic evaluation** against Nielsen's 10 (as applied to complex applications,
Kaplan NN/g 2021), with severity ratings.

**Human-agent interaction evaluation** against: Microsoft HAX guidelines (CHI 2019);
LangChain's *UX for Agents* series (Chase 2024 — chat, ambient, human-on-the-loop, agent
inbox); the automation-trust literature (Lee & See 2004; Parasuraman/Sheridan/Wickens
levels of automation; Bainbridge's ironies of automation; Dietvorst et al. 2015 on
algorithm aversion and the restorative effect of user control); NN/g's intent-based
paradigm framing (Nielsen 2023).

**Reference-product analysis** (what each is best at, what is worth stealing): GitHub PR
review, Cursor (diff review + checkpoints), Vercel (deployment pipeline visibility,
Geist), Linear (speed, keyboard, opinionated states), v0/Lovable/Bolt (vibe-coder loop),
Intercom Fin / business-AI setup flows, Stripe (test/live mode, key management), LangSmith
(agent observability), Retool/Figma (workbench zoning), n8n (node graphs — as a caution).

**Vibe-coding context.** Karpathy's framing (2025): the vibe coder "forgets the code even
exists"; the professional reads every diff. Plus the METR RCT (2025): experienced
developers were 19% *slower* with AI tools while *feeling* faster — perception and reality
diverge, so trust surfaces must show ground truth, not vibes. Both audiences are real;
they need one product at two altitudes (P2), which the current tree declares but does not
implement.

---

## 2. Product truth: what the backend can actually do

The redesign must be designed against this table, not against the contract docs.

| Capability | Backend state | Studio exposure today |
|---|---|---|
| Auth, orgs, RBAC (4 roles, 32 permissions) | full | login/signup only; **no members UI at all** |
| Projects CRUD | full | create/list only; **no rename/delete UI** (API exists) |
| GitHub App install + repo listing | full | good: install → searchable picker → select |
| Repository analysis (LLM `WebsiteAnalyst`) | full | partial: candidates + confidence, no *reasons* shown |
| Deterministic integration pipeline → branch + PR | full | partial: dry plan list, polling run, silent diff |
| Persisted run change set (C12) | full | consumed, but fetch failures silently dropped |
| Knowledge upload/chunk/embed/query | full | good bones; hardcoded metric; no grounding story |
| Assistant config + mock preview | full | good forms; **preview is a fiction** (§4.3) |
| **Public chat runtime (visitor sessions, citations, rate limits)** | **full** | **zero — not reachable from the Studio** |
| **Conversations/Messages (visitor memory)** | **full** | **zero** |
| **Usage ledger + org budget (5 states)** | **full** | HUD chip + Activity stage only; no per-run cost, no warnings surfaced |
| AgentRun + tool-call records | full | good: Activity stage + drawer (best surface in the app) |
| SSE audit stream | full | right-rail feed (4 items) + graph pulses |
| Memberships API | full | **zero** |
| Notifications | none | dead bell with permanent dot |

**Consequence for IA:** the LIVE mode currently contains a key, an origins list, and a
code snippet — while the backend holds conversations, citations, usage, budget and rate
limits. LIVE is a settings page cosplaying as an operations surface.

---

## 3. The current UI as implemented

(For the full inventory see the exploration notes; this is the decision-relevant summary.)

- **Four routes.** `/` (splash redirect), `/login`, `/signup`, `/studio`. Everything below
  `/studio` is client state — **no URLs for stages, no deep links, no refresh-safe state,
  no shareable run review**. Browser back does nothing inside the product.
- **Shell:** header (brand, project selector, BUILD/CONNECT/LIVE segment, stream dot, ⌘K,
  dead bell, account) · left rail `ProjectNavigation` (8 stages) · center `max-w-5xl`
  (GraphBar + stage view) · right rail `StudioStageWorkspace` (pins + node inspector + 4
  activity items) · bottom StatusHUD (stream, run status, cost).
- **Stage model:** overview (graph), website (GitHub connect + analysis), knowledge,
  assistant, integration (plan/run/PR/diff/history), preview (public key/origins/snippet),
  activity (telemetry), settings (stub text). Gating: knowledge←website←assistant←
  integration←preview; locked stages are **clickable** and render a dependency card.
- **The graph:** SVG star, central Brain + 8 satellites, edge pulses on SSE events,
  node-click selects (does not navigate); GraphBar chips navigate *back to overview*.
- **Design system:** hand-rolled (no Radix/shadcn), token-based, dark/light with dark as
  SSR default, Geist + Geist Mono. ~35 ui components, **16 exported-but-unused**,
  `ToastProvider` complete but **never mounted** — zero toasts in the product.
- **Data:** four React contexts (session/navigation/activity/readiness); no shared cache —
  `useProjectTelemetry` is instantiated ~4× per page, `websiteIntegrationApi.get` ×4;
  pinned stages and all navigation state are **in-memory only**.

---

## 4. Critical findings — defects and dishonesties

Severity: **B**locks trust or task · **H**igh friction · **M**edium · **L**ow.
Every item is reachable by the code as it runs today.

### 4.1 Truthfulness violations (P1 broken)

| # | Sev | Finding | Where |
|---|---|---|---|
| T1 | **B** | **The assistant preview is a fiction.** The mock shows a full chat panel with a canned grounded answer. The generated artifact is a *launcher button only* — no chat UI, no runtime call. A user configures, previews, ships… and the merged PR contains a button that opens nothing. The preview promises what the product does not deliver. | `AssistantPreview.tsx` vs `artifacts.py` (FussionAssistant.tsx = launcher only) |
| T2 | **B** | **The runtime snippet points at the wrong origin.** `fetch("${window.location.origin}/api/v1/public/chat")` uses the *Studio's* origin, not the API's. Copy-paste fails in every environment where they differ (dev: 3000 vs 8000). The one piece of code we hand users is broken. | `PreviewStageView.tsx:73` |
| T3 | **H** | **Hardcoded "384-dim (Cosine)"** metric regardless of the configured embedding provider (Gemini is a real provider now). | `KnowledgeStageView.tsx:168` |
| T4 | **H** | **Memory graph node is permanently fake** — hardcoded `{state:'idle', detail:'Not configured'}`; can never change. Decorative wiring on a canvas whose IA doc says "truth or nothing." | `agentGraphModel.ts:172` |
| T5 | **H** | **"Verified Source" / "Credentials Encrypted" / "Grounding: Verified Active"** badges assert states the UI never verified (e.g. readiness bootstrap swallows 500s into "not connected"). | `WebsiteStageView`, `readinessContext.tsx:105-117` |
| T6 | **M** | **A hardcoded human being** renders in the account menu when the user object is missing: `'Abel Byamukama' / 'abel@example.com'`. | `AccountIdentity.tsx:14-15` |
| T7 | **M** | `PullRequestInfo.status` hardcoded `"open"` server-side; the UI inherits the lie if a PR is closed/merged. | backend `website_integrations.py` |

### 4.2 Broken interactions

| # | Sev | Finding | Where |
|---|---|---|---|
| X1 | **B** | **Create-project modal never closes on success** — the cleared form stays open over the studio. Test asserts the project appears, not that the modal closes. | `CreateProjectModal.tsx:84-95` |
| X2 | **H** | **Diff and PR fetches silently swallowed** after a run completes — the diff section just never appears, indistinguishable from "no changes". | `useIntegrationStage.ts:103-121` |
| X3 | **H** | **No-op dismiss buttons** (visible X, wired to `() => undefined`) on integration and preview error banners. | `IntegrationStageView.tsx:111`, `PreviewStageView.tsx:90` |
| X4 | **H** | **Dead notification bell** with a permanently visible dot — an affordance that always says "something needs you" and does nothing. | `AppHeader.tsx:95-103` |
| X5 | **M** | Disabled "Profile"/"Account settings" rendered with `cursor-pointer` + hover styles. | `AccountMenu.tsx:66-85` |
| X6 | **M** | **Cancel run is vestigial** — the pipeline runs synchronously in-request; cancel only flips a stuck row. The dialog copy half-admits this; the control shouldn't exist until cancellation is real. | `useIntegrationStage.ts` + backend pipeline |
| X7 | **M** | Repo picker fetches page 1 / 100 with **no pagination UI**; >100 repos unreachable. | `useWebsiteStage.ts:57` |
| X8 | **M** | **Gated stages are clickable dead ends** — nav never disables; the user clicks, gets a dependency card, clicks the CTA. Error *correction* where error *prevention* is free (Nielsen #5). | `ProjectNavigation.tsx`, `stageStatus.ts` |

### 4.3 Structural / architectural UX debt

| # | Sev | Finding |
|---|---|---|
| S1 | **B** | **No URLs.** Stage, selected run, open drawer — all in-memory. Refresh loses everything; a run failure can't be linked to a teammate; browser Back exits the product. For a *professional* audience this is disqualifying. |
| S2 | **B** | **The run has no home.** The pipeline is synchronous (30–60s blocked POST), progress is a 2.5s poll of one status word, SSE carries only coarse lifecycle events *after the fact*. No step checklist, no elapsed time, no "what's happening", no deep-linkable run page. The product's core act is illegible while it happens (NN/g complex-app #1; LangChain "show your work"). |
| S3 | **H** | **LIVE mode is hollow.** Backend holds conversations, citations, usage, budget, rate limits; the stage shows a key, origins, and a broken snippet. There is no "your assistant answered 12 visitors today" moment — the payoff of the entire product is invisible. |
| S4 | **H** | **No test loop.** The public chat endpoint works *today*; the Studio offers no way to talk to the assistant being built. The vibe coder's single most trust-building interaction ("ask it a question only my business could answer") is unbuilt while the mock preview shows a fake one. |
| S5 | **H** | **Two "activity" concepts** — the right-rail SSE feed ("system activity") and the Activity stage (harness telemetry) — same word, different data, both partial. |
| S6 | **M** | **Analysis reasons are dropped.** The analyst returns ranked candidates with confidence; the UI shows % but not *why* — the explanation that lets a human judge (HAX G11: make clear why the system did what it did). |
| S7 | **M** | **No cost honesty at decision time.** Budget lives in the HUD and Activity, but "Analyze repository" (the only LLM-spending action) shows no cost expectation before or after; per-run cost isn't attached to the run that caused it. |
| S8 | **M** | **No undo anywhere.** Deletes are confirm-dialog-only (documents, origins, disconnect). Principles prefer undo (P5); the Toast system that would carry undo is unmounted. |
| S9 | **M** | **Settings is a stub** while project PATCH/DELETE and memberships APIs exist. "Manage project preferences, API credentials…" copy advertises controls that don't exist. |
| S10 | **L** | Duplicate fetching (~4× telemetry, 4× integration GET per page) — no shared query cache; will matter as SSE and live surfaces grow. |
| S11 | **L** | 16 unused components + test-only legacy views (`AssistantView` "Phase 10" badge, `KnowledgeBaseView`) — deletion-optimized the codebase is not (P10). |
| S12 | **L** | Auth pages, splashes, and the preview mock are hardcoded dark zinc/indigo — light-mode users get a dark login; theming is partial (P8). |

### 4.4 Accessibility (against P9 commitments)

- Pin affordances are hover-only (`hidden group-hover:flex`) — **dead on touch**.
- Stage changes don't move focus to the heading or reset scroll (principles require it).
- Mode segment disappears below `md` — mobile loses the lifecycle entirely.
- No `aria-live` region announces SSE arrivals or run completion.
- `--text-muted` on dark canvas is a known contrast risk (flagged in the principles'
  own baseline table, unfixed).
- Reduced-motion is handled in CSS (good) — one of the few P9 items that holds.

---

## 5. Heuristic evaluation (Nielsen 10, complex-application lens)

| # | Heuristic | Verdict | Evidence |
|---|---|---|---|
| 1 | Visibility of status | **Fails at the core loop.** | Run = one polling status word; no steps done/remaining (ArcMap pattern in NN/g); SSE coarse; readiness bootstrap conflates 500 with absent (T5). HUD exists and is good — but reports the wrong granularity. |
| 2 | Match real world | **Mixed.** | "Grounding", "Integration Point", "system instructions", `top_k`/`score_threshold` sliders — developer vocabulary imposed on business owners. Registry copy ("Next Recommended Stage") is good plain language. No altitude switch (P2 unimplemented). |
| 3 | Control & freedom | **Fails.** | No undo (S8); no restore; cancel is vestigial (X6); browser Back broken (S1). The one real reversibility unit — branch + PR — is the backend's, and the UI never says so at decision time. |
| 4 | Consistency | **Mixed.** | HUD says "Build · Connect · Automate · Live" vs header's three modes; "Assistant Voice & Widget Studio" vs "Assistant Configuration"; launcher emoji vs Geist-mono restraint; legacy test-only views on old styles. |
| 5 | Error prevention | **Fails at gating.** | Clickable locked stages (X8); mode segment jumps into gates; plan warnings are a joined text banner, not per-file annotations; origin deletion is confirm-only with no "this will break your live widget" consequence text. |
| 6 | Recognition > recall | **OK.** | Stage registry copy, HelpTips, command palette. But the run's branch name and PR URL require recall across stages (integration → preview has no hand-off). |
| 7 | Flexibility/efficiency | **Partial.** | ⌘K exists (navigate/create/switch/theme) — good start. No action verbs (run analysis, save, copy key), no keyboard nav map, no recent-runs. Pros get no accelerators the vibe coder doesn't see. |
| 8 | Minimalist design | **Fails by accumulation.** | GraphBar + left rail + right rail + HUD compete on every stage; right rail shows pins *and* inspector *and* feed; decorative canvas blocks + crosshairs behind dense forms; 16 dead components in the system. |
| 9 | Error recovery | **Fails precisely where the backend is good.** | Refusals carry excellent reasons server-side (`unsupported_reason`, 422s, protected-path reasons) — the UI shows `error_message` in a rose banner with no next step. Dead-end errors (NN/g's cardinal sin) at the exact moments the system did the *right* thing. |
| 10 | Help & docs | **Weak.** | HelpTips on integration sections — good. Nothing on assistant "system instructions" (the hardest field in the product), nothing linking analysis refusals to fixes, no docs anywhere. |

**Aggregate:** the shell's *ambition* is NN/g-compliant; the *core loop* (analyze → plan →
approve → run → PR → live) violates heuristics 1, 3, 5 and 9 — the four that decide whether
users trust automation.

---

## 6. Human-agent interaction evaluation

**Against HAX:** G1/G2 (make clear what it can do / how well) — the analysis candidates
show confidence but not capability boundaries (S6); G9 (efficient correction) — a wrong
candidate can be overridden ("Use this"), good, but a *refusal* offers no correction path;
G11 (why did it do that) — reasons dropped; G16 (convey consequences) — "Run integration"
dialog lists file counts but not consequences (a branch is created; failure leaves it;
default branch untouched); G17 (global controls) — budget exists server-side with five
states and the UI has no guardrails surface beyond a progress bar in Activity.

**Against LangChain's agent-UX taxonomy:** Fussion's engineering loop is an *ambient*
agent pattern (long task, human-on-the-loop): it needs **(a) show all steps** — absent
during runs; **(b) an agent inbox** — the notification surface where the system asks for
help (analysis refused, budget warning, run failed) — the bell is dead; **(c) correction
from a step** — re-run exists (whole-run only), which is honest for a deterministic
pipeline. The visitor runtime is *non-streaming chat* — Chase's point that non-streaming
is fine *when trust is established* applies, but the Studio never lets you establish it
(S4). B7 (SSE streaming) is already planned backend work; the Studio must be ready.

**Against trust research:** Dietvorst et al. — users forgive an erring algorithm they may
*review and modify*; Fussion's approve-the-plan gate is exactly the right trust mechanism
and is currently a `ConfirmDialog`. Lee & See — calibrated trust needs *process*
visibility (how it works) and *performance* visibility (how it did): the UI shows neither
per run. Bainbridge — if the human must take over on failure (merge conflict, refusal),
the UI must have kept them fluent enough to do so; today's dead-end banners fail this.

**The METR lesson, applied:** users will *feel* the integration worked. The Studio's job
is to show ground truth anyway — what changed, what was checked, what was **not** checked
(the PR body already says it; the Studio doesn't).

---

## 7. Two-audience journey walkthroughs

### 7.1 The vibe coder (business owner, non-developer)

> "I want a working assistant on my website."

1. **Signup** → dark-only auth screen (light-mode users: jarring). **H**
2. **Create project** → modal doesn't close; user closes it manually, slightly worried. **B**
3. **Connect GitHub** → best flow in the product. Install screen is GitHub's; repo picker
   is clear. First moment of genuine delight. ✓
4. **Analyze** → "Framework: nextjs-app-router · Integration Point: src/app/layout.tsx" —
   jargon wall. Confidence % with no *why*. If refused: amber reason, no "what now". **H**
5. **Knowledge** → upload works; chunk inspection is developer-grade but harmless;
   "Embeddings 384-dim" is noise to them; retrieval test with `top_k` sliders is a
   developer tool with no plain-language framing. **M**
6. **Assistant** → forms are clean; "System instructions (max 5000)" is the hardest
   writing task in the product with zero scaffolding; preview is a lie (T1) that will
   burn them after merge. **B**
7. **Integration** → plan = file paths they can't evaluate; confirm; spinner; then… a PR
   link. **What do I do on GitHub? Nothing tells them.** The hand-off to "merge this,
   then deploy" — the single most important instruction in their journey — is absent. **B**
8. **Live** → a key, an origins form, a broken snippet. No "it's working", no visitor
   activity, no test chat. They leave the Studio to find out if it works. **B**

**Verdict:** the vibe coder can *complete* the journey but trusts nothing after the repo
picker, and is abandoned at the two moments of maximum anxiety (did the PR work? is it
live?).

### 7.2 The professional (developer / agency)

> "What exactly will change in my repo, and what did it cost?"

1. No URL to the run, the diff, or the project — can't share, can't bookmark, Back exits. **B**
2. Plan review: paths + warnings, **no diff preview before running**, no per-file expand,
   no base SHA shown (it exists in `plan_summary`). Approving blind. **B**
3. During run: one status word; no step narrative; can't leave and come back safely
   (state in memory; SSE reconnect is fine, but there's no run page to return *to*). **H**
4. After run: diff fetch can silently fail (X2); PR status hardcoded "open" (T7);
   per-run cost not attached (S7); failed run's leftover branch acknowledged only in
   cancel-dialog copy. **H**
5. Guardrails: budget bar in Activity, but no surface for protected paths/origins/policy
   as a coherent story; the graph's Guardrails node hardcodes its list. **M**
6. Efficiency: ⌘K is nav-only; no `g w/k/a/i/l` map; no bulk anything; 4× duplicate
   telemetry fetches visible in the network tab. **M**
7. The good: AgentRun drawer (tool-call timeline, prompt hash, model+version, cost) is
   genuinely LangSmith-grade. Proof the team can build pro surfaces. ✓

**Verdict:** the professional is offered a beginner's UI with the escape hatches removed
(no URLs, no raw state, no diff-before-approve). The one pro surface that exists
(telemetry) is buried as stage 7 of a wizard.

---

## 8. Reference analysis — what the best tools do, and what to take

| Reference | What they're best at | Steal this | Reject this |
|---|---|---|---|
| **GitHub PR** | The review surface: files-changed tree, per-file diff, checks, conversation; the PR as the unit of trust | Per-file diff review as the post-run home; "checks" language (Fussion's validator results *are* checks); deep-linkable everything | — |
| **Cursor** | Diff review per file/hunk, **checkpoints** (restore to before agent ran), command approval with consequence text | The approval gate's consequence copy; "restore point" framing (Fussion's = the base SHA + branch; show it) | Per-hunk accept/reject (overkill for a 3-file deterministic change) |
| **Vercel** | Deployment as a legible pipeline: each step a row with logs, durations, deep links; Geist restraint | Run page = pipeline rows (resolve → read → plan → generate → validate → branch → PR) each with timestamp and outcome | — |
| **Linear** | Speed as a feature; keyboard map; opinionated state names; nothing inert | Zero dead controls policy; full keyboard map; states that are always real | — |
| **v0 / Lovable / Bolt** | The vibe loop: prompt → live preview → iterate; preview is *real* (their preview runs the code) | **The test chat must be real** (call the actual runtime); "what do you want to change?" iteration framing on the assistant stage | Chat-as-the-only-interface (Nielsen: half the population can't prompt well; forms win for configuration) |
| **Intercom Fin** | Business-facing AI setup: checklist onboarding, "train" sources, **test panel**, go-live toggle, then performance | Go-live checklist (key ✓ origins ✓ merged ? answering ✓); the test panel as a permanent LIVE fixture; "is_enabled" as a celebrated toggle, not a switch in a form | — |
| **Stripe** | test/**live mode** as a global, visible switch; key management UX (reveal once, named keys) | BUILD vs LIVE *is* Fussion's test/live — make the mode switch carry that weight; public key presentation is already close (CopyableField) | — |
| **LangSmith** | Run detail: ordered tool calls, cost, hashes — the "show your work" reference | Already matched by the AgentRun drawer; extend the pattern to *integration* runs | — |
| **Figma/Retool** | Workbench zoning (rail/canvas/inspector) | The 3-zone shell is right; keep it | The graph-as-canvas when topology is fixed (see §9.1) |
| **n8n/Make** | Node graphs | Edge-state honesty idea (already in STUDIO-IA) | User-drawn wiring; graphs whose layout is the user's job |
| **Devin** | Ambient run timeline with rewind/correct | The run timeline concept; skip rewind (deterministic pipeline — re-run is the correct primitive) | — |

**Meta-finding:** every trusted tool in this class converges on the same four primitives —
**a review surface, a legible progress narrative, a real test loop, and an honest
after-action record.** Fussion has the backend for all four and the UI for none.

---

## 9. Gap analysis

### 9.1 The hero-metaphor decision (resolves STUDIO-PRINCIPLES §12.1/§12.3)

**Finding:** the two governing docs disagree about what the Studio *is*, and the tree
picked the weaker one.

- The **graph** (STUDIO-IA) is a fixed star: Brain + 8 satellites, always the same shape.
  Its information content is *status*, not *structure* — and status doesn't need pan/zoom,
  a 16:9 canvas, or node-selection state. Two nodes are decorative (T4). The IA doc's own
  honesty rule ("no green without a real successful call") is violated by its flagship
  surface.
- The **pipeline** (STUDIO-PRINCIPLES §5 hero) maps 1:1 to the product's value chain and
  to real backend objects: Repository → Analysis → Plan → Change Set → Validation → PR.
  Every stage of it is inspectable truth. It is the run cockpit *and* the approval gate.

**Decision (taken, §14.1):** **the pipeline is the hero; the graph is demoted to an
ambient status strip** (the GraphBar direction, done honestly: drop fake nodes, every
chip backed by a real check, click → the owning stage). The overview page becomes the
**project command surface**: journey state, the status strip, "next action", recent
runs, budget — not a fullscreen SVG.

### 9.2 The master gap table

| Gap | Today | Needed | Size |
|---|---|---|---|
| **G1 URLs & deep links** | everything in-memory | nested routes per stage + `/runs/[id]`; refresh-safe; shareable | L (foundation) |
| **G2 Run home** | polling status word | deep-linkable run page: pipeline step rows, durations, outcome, diff, PR, cost, failure with recovery | M |
| **G3 Approval gate** | ConfirmDialog over file list | designed review: per-file expand, warnings per file, consequence text, base SHA, "what Fussion will NOT do" | M |
| **G4 Real test chat** | mock preview lie | control-plane-authenticated test chat running the real retrieve→generate pipeline (small backend slice) + streamed when B7 lands | M |
| **G5 LIVE operations** | key + origins + broken snippet | go-live checklist, test panel, visitor conversations (read), usage/budget, activity | M |
| **G6 Refusal/failure surfaces** | dead-end banners | designed refusal cards: reason (already excellent server-side), what it means, what to do, who to contact | S |
| **G7 Onboarding** | hero + modal bug | journey map (3 moves, time estimates), endowed-progress checklist, GitHub-first path | S |
| **G8 Undo & toasts** | confirm-only; Toast unmounted | mount ToastProvider; undo for doc delete / origin remove; keep confirms for irreversible | S |
| **G9 Notifications** | dead bell | SSE-fed inbox (run failed, PR created, budget warning, analysis refused) or remove the bell until real | S |
| **G10 Settings/members** | stub | project rename/delete (API exists), org members (API exists), budget visibility | M |
| **G11 Altitude model** | declared, absent | plain-language layer over jargon (progressive disclosure: "Integration point" → "the file where your site's layout lives — src/app/layout.tsx"); pro layer: raw state, cost, SHAs | M (cross-cutting) |
| **G12 Plan diff preview** | paths only | optional pro altitude: generate artifacts at plan time (deterministic — no new risk) and show diffs pre-approval; backend slice | M (deferrable) |
| **G13 Progress events** | coarse audit only | backend: pipeline emits step events into the audit stream; UI renders rows (until then, the run page renders the known-step checklist honestly: "in progress — validating") | S–M (backend) |
| **G14 Design-system hygiene** | 16 dead components, token drift, unthemed auth | delete or mount; single token source; theme the auth stack; contrast fix | S |
| **G15 Data layer** | 4× duplicate fetching | one query cache (or context-level dedupe) before LIVE surfaces multiply requests | S |

---

## 10. Proposed information architecture

### 10.1 Routes (real URLs, modes preserved as layout state)

```
/login · /signup
/projects                              gallery: cards w/ status strip, last run, health
/studio/[projectId]                    overview (command surface)
/studio/[projectId]/website            BUILD · source
/studio/[projectId]/knowledge          BUILD · grounding
/studio/[projectId]/assistant          BUILD · voice (+ real test chat)
/studio/[projectId]/connect            CONNECT · the workbench: plan → approve → run → PR
/studio/[projectId]/connect/runs/[runId]   run home (deep-linkable; review, diff, cost)
/studio/[projectId]/live               LIVE · go-live checklist, test, conversations, usage
/studio/[projectId]/activity           runs + audit + telemetry (merges S5's two concepts)
/studio/[projectId]/settings           project settings, danger zone
/org/settings                          org, members, budget   (later slice)
```

- Modes BUILD/CONNECT/LIVE remain the header segment; each maps to a route group, so the
  URL *is* the mode. Locked stages resolve to their URL and render the gate — deep links
  to locked stages work and teach (recognition, not recall).
- `overview` stops being a stage among stages; it's the project's front page.

### 10.2 The shell (unchanged zones, tightened contents)

```
┌────────────────────────────────────────────────────────────────────┐
│ Fussion  [Org ▾ / Project ▾]        ⌘K   BUILD · CONNECT · LIVE    │
│                        status strip (honest graph chips)  🔔 inbox │
├──────────┬──────────────────────────────────────────────┬──────────┤
│ RAIL     │  WORK SURFACE                                │ INSPECTOR│
│ Overview │  (stage content; one width per breakpoint)   │ context: │
│ ─ BUILD  │                                              │ run ·    │
│ Website  │                                              │ node ·   │
│ Knowledge│                                              │ approvals│
│ Assistant│                                              │          │
│ ─ CONNECT│                                              │          │
│ Connect  │                                              │          │
│ ─ LIVE   │                                              │          │
│ Live     │                                              │          │
│ Activity │                                              │          │
│ Settings │                                              │          │
├──────────┴──────────────────────────────────────────────┴──────────┤
│ HUD: ● stream · run state · branch · $spend/$limit · saved         │
└────────────────────────────────────────────────────────────────────┘
```

Changes from today: bell becomes a real inbox (G9); status strip moves into the header
(honest graph chips, fake nodes removed); inspector is reserved space showing *context*
(run detail on connect, test chat on assistant, approvals when present) rather than pins
+ feed + inspector competing; rail stages show lock state upfront (X8 fixed by
prevention, not correction).

### 10.3 Stage ownership (each backend capability gets exactly one home)

| Surface | Owns |
|---|---|
| Website | GitHub connection, analysis (with reasons), target selection |
| Knowledge | documents, chunks, retrieval test (framed in plain language) |
| Assistant | identity/appearance/behavior + **real test chat** |
| Connect | plan review (approval gate), run progress, PR hand-off, run history |
| Run page | one run: steps, diff, cost, failure recovery |
| Live | go-live checklist, key+origins, test, conversations, usage |
| Activity | audit feed + agent runs + usage (the pro observability floor) |
| Settings | rename/delete, (later) members |

---

## 11. Key wireframes

### 11.1 Overview (command surface)

```
┌─────────────────────────────────────────────────────────────┐
│ Acme Store                                    BUILD ····○○ │
│ "One assistant, grounded in your docs, live on your site." │
│                                                             │
│ ┌─ Your path ────────────────────────────────────────────┐ │
│ │ ✓ 1. Connect your website        acme/store · main     │ │
│ │ ✓ 2. Ground it in your knowledge  4 docs · 212 chunks  │ │
│ │ ● 3. Give it a voice              draft — unsaved      │ │
│ │ ○ 4. Ship it to your site         locked until voice   │ │
│ │ ○ 5. Go live                                             │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─ Next ─────────────────────────────────┐ ┌─ Status ────┐│
│ │ Finish the assistant's voice.          │ │ ▣ brain  ok ││
│ │ ~5 min. Then you can ship it.          │ │ ▣ repo   ok ││
│ │                    [ Open Assistant → ]│ │ ▣ kb     ok ││
│ └────────────────────────────────────────┘ │ ▣ budget 71%││
│ ┌─ Recent ───────────────────────────────┐ └─────────────┘│
│ │ PR #14 opened · 2d ago · $0.00 · view  │                │
│ │ Analysis completed · 3d ago · $0.41    │                │
│ └────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 Connect — the approval gate (money screen)

```
┌─────────────────────────────────────────────────────────────┐
│ CONNECT · Ship the assistant to acme/store                  │
│                                                             │
│ ┌─ Plan · base a1b2c3d (main, read 2 min ago) ────────────┐ │
│ │                                                         │ │
│ │ CREATE  src/components/fussion/FussionAssistant.tsx  [▾]│ │
│ │ CREATE  src/lib/fussion-assistant.ts                 [▾]│ │
│ │ MODIFY  src/app/layout.tsx        1 import · 1 block [▾]│ │
│ │                                                         │ │
│ │ ⚠ Analysis is 2 commits behind main — [re-analyze]      │ │
│ │                                                         │ │
│ │ What Fussion will do:     What it will NOT do:          │ │
│ │ · branch fussion/integration/<id>   · touch main        │ │
│ │ · commit the 3 files above      · install dependencies  │ │
│ │ · open 1 pull request           · run your build        │ │
│ │                                                         │ │
│ │              [ Run integration ]  est. ~40s · $0.00*    │ │
│ │              *deterministic — no model calls            │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 11.3 Run home (deep-linkable)

```
/studio/acme/connect/runs/9f3e2d1c
┌─────────────────────────────────────────────────────────────┐
│ Run 9f3e2d1c · acme/store                    ● VALIDATING   │
│ Started 14:02:11 · 38s elapsed · branch fussion/integration/9f3e2d1c
│                                                             │
│ ✓ Resolve credentials            0.4s                       │
│ ✓ Read repository @ a1b2c3d      1.2s                       │
│ ✓ Plan · 3 files                 0.1s                       │
│ ✓ Generate artifacts             0.2s                       │
│ ● Validate                       …                          │
│ ○ Create branch & commit                                    │
│ ○ Open pull request                                         │
│                                             [ Cancel ]*     │
│ *when cancellation is real; until then this control         │
│  does not exist (X6)                                        │
├─ After completion ──────────────────────────────────────────┤
│ ✓ PR #14 opened →  github.com/acme/store/pull/14            │
│                                                             │
│ Files changed (3)                            Cost $0.00     │
│ ▾ src/app/layout.tsx  (+6 −0)                                 │
│   [unified diff — the persisted change set, never derived]  │
│                                                             │
│ Next: review & merge on GitHub → deploy → set allowed       │
│ origins in Live.                       [ Open Live → ]      │
└─────────────────────────────────────────────────────────────┘
```

Failure variant: the failed step turns rose; below it a **recovery card**: the server's
refusal reason verbatim (they're good), what it means in plain language, and the one
action that resolves it ("Re-run analysis", "Reconnect GitHub", "Choose another target").

### 11.4 Assistant — with the real test loop

```
┌──────────────────────────────┬──────────────────────────────┐
│ Identity / Appearance /      │ Test your assistant          │
│ Behavior forms (as today,    │ ┌──────────────────────────┐ │
│ plus in-field guidance:      │ │ 🟢 live · grounded in    │ │
│ "System instructions: what   │ │    4 documents           │ │
│ should it always do? Never   │ │                          │ │
│ do? Write it like a job      │ │ You: Do you deliver to   │ │
│ description."                │ │      Kampala?            │ │
│                              │ │ A: Yes — delivery within │ │
│ [ Unsaved changes · Save ]   │ │ Kampala is next-day…¹    │ │
│                              │ │ ¹ delivery-policy.pdf p2 │ │
│                              │ │                          │ │
│                              │ │ [ Ask…            ]      │ │
│                              │ └──────────────────────────┘ │
│                              │ Powered by the real runtime. │
│                              │ Unsaved changes apply on     │
│                              │ save. [why?]                 │
└──────────────────────────────┴──────────────────────────────┘
```

This replaces the mock. It calls a control-plane-authenticated test endpoint (small
backend slice — §12 G4) that runs the *same* resolve→retrieve→generate pipeline, so what
the user tests is what visitors get. When B7 streaming lands, this streams.

### 11.5 Live

```
┌─────────────────────────────────────────────────────────────┐
│ LIVE · Acme Store                         Assistant ● ON    │
│                                                             │
│ ┌─ Go-live checklist ────────────────────────────────────┐  │
│ │ ✓ Pull request created           PR #14                │  │
│ │ ? Pull request merged            check GitHub →        │  │
│ │ ✓ Allowed origin set             https://acme.ug       │  │
│ │ ✓ First visitor question answered  2h ago              │  │
│ └────────────────────────────────────────────────────────┘  │
│ ┌─ Today ────────────┐ ┌─ Public key & origins ──────────┐  │
│ │ 31 conversations   │ │ fsk_live_…          [copy]      │  │
│ │ 4.1k tokens · $0.06│ │ https://acme.ug     [remove]    │  │
│ │ budget: 71% of $25 │ │ [ + add origin ]                │  │
│ └────────────────────┘ └─────────────────────────────────┘  │
│ ┌─ Recent conversations ─────────────────────────────────┐  │
│ │ "Do you deliver…" · 3 turns · 2 citations · 2h ago     │  │
│ └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

("PR merged" is honest: Fussion can't know until GitHub tells it — the item links out and
says so, or a later webhook slice makes it real.)

---

## 12. Interaction model — what gets added

1. **Feedback taxonomy, implemented as designed** (P6/P7): mount `ToastProvider` (passive
   success + undo actions); banners reserved for action-required; inline validation on
   fields; determinate step-checklist for runs; `aria-live="polite"` region announcing SSE
   arrivals and run completion.
2. **Undo before confirm** (P5): document delete and origin remove become toast-undo;
   disconnect/reset/rerun keep `ConfirmDialog` with consequence-specific copy and
   outcome-labeled buttons.
3. **Keyboard map** (pro altitude, hidden from novices): `g o/w/k/a/c/l` navigate, `⌘K`
   palette gains verbs (Run analysis, Run integration, Save assistant, Copy public key),
   `?` opens the map. Focus moves to the stage heading on navigation; scroll resets.
4. **Lock upfront** (X8): rail shows lock glyphs with the unlock condition on locked
   stages; clicking still works (deep links) but expectation is set before the click.
5. **Honest progress** (S2/G13): run page renders the known pipeline steps; states are
   real (from run status + SSE events); where granularity doesn't exist yet the UI says
   "in progress" — never fabricated substeps. Backend progress events upgrade the same
   rows later without redesign.
6. **Cost at decision time** (S7): analysis button shows "last analysis cost $0.41";
   run page attaches cost; budget warnings surface in the inbox (G9).
7. **Consequence copy at gates** (HAX G16): every confirm states what happens, what
   doesn't, and what is reversible ("a failed run leaves its branch; nothing touches
   main; the PR is yours to close").
8. **Hand-offs, not dead ends**: every completion names the next move (PR → merge → Live;
   refusal → the fixing action; analysis → "choose a target"). Every error has one action.
9. **Empty states that teach**: each stage's empty state = one sentence of what this is,
   one of why, one action.
10. **Reduced motion & theming parity**: motion off → static edge colors; auth stack and
    splashes tokenized; `--text-muted` dark contrast fixed.

---

## 13. Redesign plan — Step F slices

Per the repo's step/slice discipline. Tiers per `CLAUDE.md` §9.0. Sequenced: truth and
foundation first, money moment second, new surfaces third, altitude last.

| # | Slice | Tier | Done when | Gaps |
|---|---|---|---|---|
| **F0** | **Foundations & truth sweep** | 3 | X1–X7, T2–T7 fixed; ToastProvider mounted; dead components deleted or mounted; auth stack themed; contrast fixed; no-op dismisses removed; snippet origin from config | T2–T7, X1–X8, S11/S12/S14 |
| **F1** | **URL architecture** | 2 | Nested routes as §10.1; stage = URL; refresh-safe; run deep link `/connect/runs/[id]`; browser Back works; focus-to-heading on navigation | G1, S1 |
| **F2** | **The run home + approval gate** | 2 | Connect stage rebuilt as §11.2/§11.3: step checklist from real states, persisted diff on the run page, refusal recovery cards, PR hand-off block, cancel removed until real, consequence copy | G2, G3, G6, S2, X6 |
| **F3** | **Real test chat** | 1* | Backend: authenticated `POST /assistant/test-chat` running the real pipeline (no origin requirement); frontend: assistant-stage panel per §11.4; mock preview deleted. *Tier 1 because it touches a prompt path; reviewer round required. | G4, T1, S4 |
| **F4** | **LIVE operations surface** | 2 | Go-live checklist, key+origins (fixed snippet), usage/budget cards, recent conversations read view (from `Conversation`/`Message`), activity consolidation (S5) | G5, S3, S5 |
| **F5** | **Onboarding & overview** | 2 | Command-surface overview per §11.1 (journey state, honest status strip replacing fullscreen graph, next action, recent runs); create-modal fix verified; endowed-progress checklist | G7, §9.1 |
| **F6** | **Inbox + notifications** | 2 | SSE-fed notification center (run failed, PR created, budget warning, analysis refused); dead bell removed until F6 lands | G9 |
| **F7** | **Altitude layer + keyboard** | 2 | Plain-language progressive disclosure on jargon surfaces; pro raw-state blocks (SHAs, IDs, costs) in inspector; keyboard map + palette verbs | G11 |
| **F8** (deferrable) | **Plan diff preview** | 2 | Backend: plan-time artifact generation (deterministic, read-only) → pre-approval diffs for the pro altitude | G12 |
| **F9** (backend-led) | **Pipeline progress events** | 2 | Step-level events in the audit stream; run page rows consume them (UI already built in F2) | G13 |

**Explicit non-goals for Step F:** per-hunk diff editing; user-drawn graph wiring; members
UI polish beyond the API surface; streaming in the Studio test chat (waits on B7);
webhook-driven "PR merged" state; a second design language of any kind.

**Dependencies noted:** F4's conversations view needs a control-plane conversations list
endpoint (small backend slice — `Conversation`/`Message` exist). F3 needs the test-chat
endpoint. Both are small and should ride in their slices, not become steps.

---

## 14. Decisions (taken 2026-09-14)

1. **Hero metaphor — DECIDED: pipeline-as-hero.** The Integration Workbench
   (Repository → Analysis → Plan → Change Set → Validation → PR) is the Studio's hero;
   the agent graph is demoted to an honest status strip (fake nodes removed, every chip
   backed by a real check). F5 implements this per §9.1.
2. **The mock preview — DECIDED: delete it.** Once the real test chat exists (F3), the
   mock is removed entirely. Nothing in the UI shows what the product doesn't do.
3. **Conversations in LIVE — DECIDED: read-only recent-conversations list in MVP scope.**
   F4 includes it (small control-plane list endpoint rides in the slice).
4. **Onboarding — DECIDED: journey map on the overview** (§11.1), not a one-time wizard.
   Works on every visit, not just first run.
5. **"PR merged" truth — OPEN (non-blocking).** Default for Step F: honest link-out
   ("check GitHub"). A webhook slice that makes it real is post-MVP unless priorities
   change.

---

## Appendix A — Research sources

- Nielsen, *AI: First New UI Paradigm in 60 Years* (NN/g 2023) — intent-based outcome
  specification; the GUI isn't dead, hybrid wins; "half the population can't prompt" →
  forms for configuration, chat for the test loop.
- Kaplan, *10 Usability Heuristics Applied to Complex Applications* (NN/g 2021) — detailed
  progress (steps done/remaining), version history, real-time previews, in-context help,
  non-dead-end errors. Basis of §5.
- Chase, *UX for Agents, Parts 1–2* (LangChain 2024) — streaming vs non-streaming chat;
  ambient agents; human-**on**-the-loop (show steps, correct from step); the agent inbox.
  Basis of §6 and the inbox slice.
- Microsoft, *Guidelines for Human-AI Interaction* (HAX, CHI 2019) — G1/G2 capability
  clarity, G9 correction, G11 why-explanations, G16 consequence conveyance, G17 global
  controls. Cited throughout §6.
- Lee & See, *Trust in Automation* (2004); Parasuraman/Sheridan/Wickens (2000); Bainbridge,
  *Ironies of Automation* (1983); Dietvorst et al., *Algorithm Aversion* (2015) — calibrated
  trust, levels of automation, takeover fluency, review-and-modify as the trust restorer.
- METR, *Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer
  Productivity* (2025) — 19% slower while feeling faster: show ground truth, not vibes.
- Karpathy, "vibe coding" (2025) + Willison's distinction — the two-altitude model's
  empirical basis.
- Product references: GitHub PR review, Cursor (checkpoints/diff review), Vercel
  (deployment pipeline, Geist), Linear (keyboard/speed/no inert controls), v0/Lovable/Bolt
  (real-preview vibe loop), Intercom Fin (business-AI setup + test panel + go-live),
  Stripe (test/live modes, key UX), LangSmith (run observability), Retool/Figma (workbench
  zoning), n8n/Make (graphs — cautionary), Devin (ambient run timeline).

## Appendix B — The five principles this audit adds to STUDIO-PRINCIPLES

1. **The pipeline is the hero.** The product is the integration; the UI must be built
   around Repository → Analysis → Plan → Change Set → Validation → PR.
2. **Surface what's built before building what's next.** Test chat, conversations, cost —
   the backend is ahead of the UI; close that gap first.
3. **Every completion hands off.** No surface ends without naming the next move.
4. **Refusals are designed screens.** The backend refuses well; the UI must refuse
   beautifully — reason, meaning, action.
5. **Two altitudes, one truth.** Plain language up top, raw state one disclosure down —
   never different data, never a dumbed-down truth.
