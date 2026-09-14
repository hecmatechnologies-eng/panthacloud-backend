# Fussion Studio — Design Principles

**Status:** governing design reference for the Studio redesign.
**Scope:** the Studio frontend (`frontend/`). It does not change the product's
architecture or backend contracts; it constrains how the interface is structured,
organised, and interacted with.
**Companion audits:** the structure/organisation/touch-point/layout audit and the
pattern research that preceded this document (see "References" for external sources).

---

## 1. Vision — a studio, not a dashboard

Fussion Studio is a **workbench where integrations get built**. It is not an admin
dashboard that happens to use cards. The interface is organised around a **canvas
with tools**, not a stack of pages:

- The **canvas** (the work surface) is the dominant element.
- **Tools** sit on a left rail; **properties and state** live in a right inspector.
- The lifecycle (`BUILD → CONNECT → LIVE`) is expressed as **modes**, not pages.
- **History, versions, and runs** are first-class, and every action is reversible.
- A real **status HUD** reports connection, run state, cost, and save state.

The existing visual language already carries this metaphor — the grid canvas, Geist
mono for technical identifiers, the purple accent, the `rounded-2xl/3xl` surfaces.
The redesign **keeps that language** and fixes the organisation around it.

---

## 2. Audiences and the altitude model

Two audiences share one product:

| | **Vibe coder** (non-developer builder) | **Professional** (developer / agency) |
|---|---|---|
| Goal | "Build me a working assistant" | "What exactly will change in my repo?" |
| Needs | Guidance, plain language, safety, no dead ends | Raw state, speed, control, diffs, cost |
| Trust earned by | Showing *why* and *what next*; never surprising | Showing *exactly what changed*; letting them override |

**Model:** *guided studio*. The workbench is always underneath; guidance is layered on
top. Use **progressive disclosure by altitude** — the simple path always works, and an
expert layer (inspector, command palette, raw state) is revealed on demand. Never two
products; never a blank canvas for a newcomer.

---

## 3. Qualities of good UI we hold ourselves to

| Quality | Source | Commitment |
|---|---|---|
| Learnability, efficiency, memorability, errors, satisfaction | Nielsen, *Usability 101* | Both audiences complete the journey; the expert path is faster, not different. |
| Visibility of status, control & freedom, error prevention, recognition over recall, flexibility | Nielsen's 10 heuristics | Every status from the backend; undo/confirm; accelerators hidden from novices. |
| Complex-app specifics: detailed progress, version history, live preview, in-context help | NN/g, *Heuristics for Complex Applications* | No generic "Please wait"; show steps done/remaining; previews as you change. |
| Aesthetic-usability effect | NN/g | Polish buys tolerance for *minor* issues only; form must serve function. |
| Progressive vs staged disclosure | NN/g | Wizard for onboarding; secondary disclosure for power; max 2 levels. |
| Response-time limits (0.1s / 1s / 10s) | NN/g | Optimistic <100ms; skeleton <1s; determinate progress + interrupt >10s; stream model output. |
| Indicators / validations / notifications | NN/g | Pick the feedback mechanism by type, urgency, action-required. |
| Confirmation dialogs | NN/g | Confirm only serious/irreversible actions; be specific; prefer undo; no default "Yes". |
| Human-AI interaction (18 guidelines) | Microsoft HAX | Set expectations; support control, scope, explanation; support recovery; convey change. |
| Laws: Fitts, Hick, Miller, Tesler, Jakob; affordances/signifiers/feedback; Gestalt | established HCI | Big targets for primary actions; fewer choices at decision points; chunk; don't move complexity onto the user; external consistency. |
| Automation trust: observability, interruptibility, reversibility, graceful degradation | Parasuraman/Sheridan/Wickens; Bainbridge; Norman | Automation must show its work, be stoppable, be reversible, and degrade to a usable manual path. |

**One sentence:** a good Fussion Studio is **truthful, controllable, legible, reversible,
and fast-feeling** — and it never asks the user to trust a machine it hasn't shown its
work for.

---

## 4. Design principles

**P1 — One source of truth.** Every status, gate, and badge derives from backend state.
No hardcoded "verified", "encrypted", or "healthy" claims.

**P2 — Progressive disclosure by altitude.** Simple path always works; expert layer on
demand. One product, two altitudes.

**P3 — Studio, not dashboard.** Dominant canvas, tools and inspector around it, modes
over pages, history and reversibility, real status HUD.

**P4 — Human-in-the-loop by default.** Plan → approve → act. The human stays in command;
automation is observable and interruptible.

**P5 — Reversible or confirmed.** Every destructive action is undoable or specifically
confirmed. `window.confirm` is banned.

**P6 — Latency choreography.** <100ms optimistic; <1s skeleton; >10s determinate progress
with a stop control; streaming for model output.

**P7 — Trust through explanation.** Show why, what changed, and what it cost. Provenance,
citations, tool logs, and commit SHAs are visible, not hidden.

**P8 — One design system.** One token source, one component language, light/dark parity,
no dead or duplicate surfaces.

**P9 — Accessible by construction.** Labels, focus management, contrast, reduced motion,
keyboard-first, ≥44px touch targets, pointer/touch/keyboard parity.

**P10 — Optimise for deletion.** A capability is removable by deleting its folder and one
registry line — including UI surfaces and stage definitions.

---

## 5. Frame and layout model

**Three stable zones, one responsive strategy.**

```
┌──────────────────────────────────────────────────────────────┐
│ App header — brand · org/project switcher · status · account   │  sticky, opaque enough
├──────────┬──────────────────────────────────────┬────────────┤
│ Tool rail│ Work surface (canvas)                 │ Inspector  │
│ (modes)  │ one width; primary action in a        │ run · cost │
│ collapse │ sticky toolbar                        │ · diff ·   │
│ to icons │                                       │ provenance │
├──────────┴──────────────────────────────────────┴────────────┤
│ Status HUD — connection · run state · cost · save state        │
└──────────────────────────────────────────────────────────────┘
```

Rules:

- **The inspector is reserved space**, collapsible to a drawer — never a conditional flex
  sibling. Content width must not change when activity arrives (no CLS).
- **One work-surface width per breakpoint.** No per-stage `max-w-3xl/4xl/5xl` jumps.
- **Modes over pages.** `BUILD · CONNECT · LIVE` swap the tool set; the canvas persists.
- **Intermediate nav pattern** below `xl`: rail collapses to a top segmented control or
  off-canvas drawer; never a narrow vertical column stacked above content.
- **One page template** (`StageLayout`) with slots: breadcrumb, mode badge, title,
  description, primary action, content, aside. No repeated four-block headers.
- **One vertical rhythm** and documented z-index scale.
- **The canvas atmosphere sits behind the work** (subtle), never competing with it.

**Hero surface (direction, subject to scope check):** an **Integration Workbench** —
`Repository → Analysis → Plan → Change Set → Validation → Pull Request` as an inspectable
pipeline where the current run animates. It is name-appropriate, makes automation legible,
and doubles as the run cockpit and approval gate.

---

## 6. Interaction standards

**Feedback taxonomy** (choose by type, urgency, action-required):

| Need | Mechanism |
|---|---|
| Input is wrong | Inline validation, tied to the field, with fix guidance |
| Element has changed / has state | Contextual indicator (dot, badge) |
| Passive success | Non-modal toast |
| Action required | Inline banner or modal (reserved) |
| Long operation | Determinate progress + step checklist + stop control |
| Model output | Streaming text |
| Background failure | Persistent, dismissible status in the HUD/inspector |

**Confirmation policy:** confirm only serious or irreversible actions; be specific about
the consequence; label buttons with outcomes ("Delete integration", not "Yes"); no default
dangerous answer; for the most dangerous actions require a nonstandard confirmation; prefer
undo over confirmation wherever possible.

**Parity:** every hover affordance has a tap and keyboard equivalent. No hover-only
actions. Minimum 44×44px targets for touch. Focus-visible everywhere. Focus trap + Escape
on all overlays. `aria-live` for async results. Stage changes move focus to the heading and
reset scroll.

**Reversibility:** draft autosave; undo/redo for editing; version history and restore for
projects/runs; the branch + PR is the reversible unit for code.

**Latency:** optimistic updates with rollback; skeletons rather than blank; determinate
progress and a cancel control for runs; streaming for chat.

**Plain language:** user-facing copy avoids internal jargon; technical terms (SHA, token,
commit) are available in the inspector with a "what's this?" affordance, not forced on
beginners.

---

## 7. Pattern catalogue (summary)

- **Layout:** app shell (3-zone), master–detail, workbench, wizard/stepper, inspector,
  split view, dashboard.
- **Navigation/menus:** side nav + collapse, tabs/segmented, breadcrumbs, command palette
  (⌘K), overflow menu, context menu, toolbar, onboarding checklist.
- **Controls:** primary/secondary/ghost/destructive buttons, split button, icon button,
  toggle, segmented control, radio/checkbox, combobox/autocomplete, sliders, dropzone,
  color picker, code editor, diff viewer, tree, data grid, timeline, log/console, badges,
  chips, tooltip, popover, modal, drawer, toast, banner, accordion, skeleton, empty state.
- **Feedback:** status indicator, validation, notification, optimistic UI, streaming,
  activity feed.
- **Automation/HITL:** plan preview, approve/refuse, diff review, "show your work" tool log,
  explainability, confidence/refusal, cost/budget meter, kill switch + retry, undo/rollback,
  progressive autonomy, guardrails.

---

## 8. What we preserve

- The token system and dual theme (see baseline below).
- Geist sans + mono convention; mono reserved for technical identifiers.
- `rounded-2xl/3xl` surfaces, `border-[var(--border)]`, `shadow-xs` card language.
- Purple accent, emerald success, rose danger semantics.
- The `BUILD → CONNECT → LIVE` narrative and the five-stage model.
- The canvas atmosphere, made subtler.

**Token baseline (current, to be formalised in Phase 0):**

| Token | Light | Dark |
|---|---|---|
| `--canvas` | `#F4F7F5` | `#06100D` |
| `--canvas-grid` | `#D7E7DF` | `#0F2A20` |
| `--surface` | `#FFFFFF` | `#101816` |
| `--surface-elevated` | `#F8FAF9` | `#151F1B` |
| `--border` | `#E5E7EB` | `#1F3A31` |
| `--text-primary` | `#0F172A` | `#F8FAF9` |
| `--text-secondary` | `#64748B` | `#94A3A0` |
| `--text-muted` | `#94A3B8` | `#62726E` |
| `--color-purple` | `#7C3AED` | `#7C3AED` |
| `--color-success` | `#16A34A` | `#22C55E` |
| `--color-danger` | `#EF4444` | `#F87171` |

*Note: `--text-muted` on the dark canvas is a contrast risk for small text and must be
raised during the Phase 0 accessibility pass.*

---

## 9. Anti-patterns (banned)

`window.confirm`; hover-only actions; hardcoded "verified/healthy" states; client-only
progress; conditional flex siblings that shift content width; a floating save bar with
magic padding; multiple sources of stage truth; dead navigation or a second design language;
generic "Please wait" for >10s operations; dead-end error messages; confirmation fatigue;
decorative elements that compete with the work.

---

## 10. Governance and quality gates

- **Every UI change:** axe/a11y pass · keyboard-only pass · no hardcoded state · responsive
  matrix · no banned anti-patterns.
- **Every phase:** usability testing with both audiences (task success, time-on-task, error
  rate, and **trust/confidence** — not just satisfaction, because aesthetics mask problems).
- **Instrumentation:** funnel completion, gate drop-off, run success/failure, cancel/retry
  use, palette adoption.
- **Design-system governance:** one token source; versioned components; new patterns require
  a documented reason. Definition of done mirrors the backend: no unverified "complete".

---

## 11. References

- Nielsen, *10 Usability Heuristics for User Interface Design* (NN/g, 1994/2024).
- Nielsen, *Usability 101: Introduction to Usability* (NN/g).
- Kaplan, *10 Usability Heuristics Applied to Complex Applications* (NN/g, 2021).
- Nielsen, *Progressive Disclosure* and *Response Times: The 3 Important Limits* (NN/g).
- Flaherty, *Indicators, Validations, and Notifications* (NN/g, 2024).
- Nielsen, *Confirmation Dialogs Can Prevent User Errors — If Not Overused* (NN/g, 2018).
- Moran, *The Aesthetic-Usability Effect* (NN/g, 2024).
- Microsoft, *Guidelines for Human-AI Interaction* (HAX Toolkit; CHI 2019).
- Parasuraman, Sheridan & Wickens, *A Model for Types and Levels of Human Interaction with
  Automation* (2000); Bainbridge, *Ironies of Automation* (1983); Norman, *Human-Centered AI*.

---

## 12. Open decisions

1. **Frame model** — stable 3-zone shell with the wizard as onboarding (recommended), or a
   task-based workspace throughout.
2. **Inspector default contents** — engineering run or live runtime.
3. **Hero surface** — conventional stage pages, or the Integration Workbench pipeline.
4. **Phase 0 scope** — foundations only, or foundations plus the mounted pipeline in one pass.
