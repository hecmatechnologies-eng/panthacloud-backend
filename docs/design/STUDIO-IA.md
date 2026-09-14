# Fussion Studio — Information Architecture

**Status:** proposed IA for the Studio redesign. Companion to `STUDIO-PRINCIPLES.md`.
**One-line thesis:** Fussion Studio is a **topology studio** — a live canvas of an agent's
capabilities wired to a central brain — not a form wizard. Figma shows static design; Fussion
shows a running agent.

---

## 1. Positioning

| | Figma | Fussion Studio |
|---|---|---|
| Canvas | static frames | a **live running agent** |
| Left panel | layers (objects) | **outliner of capabilities** |
| Right panel | properties | **config + live status + provenance** |
| Constraints | layout rules | **policy, budget, guardrails** |
| Prototype links | simulated | **real edges with real traffic** |

**The honesty rule:** every node and edge maps to real backend state, and every pulse is a real
event. An edge only goes green on a real successful call. No decorative wiring.

---

## 2. The frame

```
┌──────────────────────────────────────────────────────────────────┐
│  Fussion   [Org ▾ / Project ▾]        ⌘K   Build · Connect · Live │  Header
│                                     ● Live   $spend/$limit   ◔ ◉  │
├────────────┬────────────────────────────────────────┬────────────┤
│ OUTLINER   │                 CANVAS                 │ INSPECTOR  │
│ (layers)   │             the Agent Graph            │ (context)  │
├────────────┴────────────────────────────────────────┴────────────┤
│ ● stream · run: idle · branch · env · saved                       │  HUD
└──────────────────────────────────────────────────────────────────┘
```

- **Header:** brand · **workspace (org) switcher** · **project switcher** · ⌘K search · mode
  segment (Build / Connect / Live) · live-stream dot · **cost/budget chip** · notifications ·
  account. No fake controls.
- **Left — outliner:** the agent's capabilities as a tree with status dots. Navigation *is* the
  topology; selecting an outliner row selects the node on the canvas.
- **Center — canvas:** pan/zoom, minimap, selection.
- **Right — inspector:** the selected node/edge: real config, live status, provenance, actions.
  Nothing selected → project readiness.
- **Bottom — HUD:** stream state, run state, branch, environment, save state.

---

## 3. Node taxonomy

| Node | Represents | Backend |
|---|---|---|
| **Brain** | the model | `ModelGateway`, `ModelUsage` |
| **Website** | integration target | `WebsiteIntegration` |
| **Knowledge** | grounding store | documents, chunks, embeddings |
| **Skill** | framework recipe | `skills/integrations/*` |
| **Integration** | the built change | `IntegrationRun`, pull request |
| **Guardrails** | policy & budget | budget thresholds, protected paths, origins |
| **Runtime** | public visitor plane | `/public/chat`, allowed origins |
| **Memory** | conversation + project memory | memory tiers |

## 4. Edge states

| State | Meaning |
|---|---|
| dashed grey | not configured |
| amber, slow pulse | connecting / working |
| **green + moving bits** | healthy; last real call succeeded |
| **red, static** | last call failed / refused |
| shield glyph | write action; requires approval |
| lock glyph | credential-backed; value never shown |

Edges are **derived**, not user-drawn. Configuring a node wires its edge automatically.

---

## 5. The narrative: plain brain → wired

- **Empty project:** one dim **Brain** node, breathing slowly — *"a brain with nothing wired to it
  yet"* — and one action: connect knowledge or a website.
- Each completed capability **materialises a node** and **grows an edge** with a wire-in animation.
- Each edge carries a **real health check** (retrieval test, repo connection, budget check), so
  green means verified.
- The old stage checklist becomes the graph's growth. The wizard survives as a **guided
  highlight** that spotlights the next unwired node.

---

## 6. Project & workspace management

- **Workspace (org) → Projects.** One project = one agent + one website integration.
- **Project switcher** in the header; **"All projects"** opens a **gallery** (cards with a graph
  thumbnail, health, last run) — never a dead end.
- **Personal workspace** is a default org; team orgs sit beside it.
- **Project settings** live on the Settings node: name, archive/delete, members, secrets, origins,
  budget.

## 7. Access & policy

- **Members & roles** matrix (OWNER / ADMIN / MEMBER / VIEWER); destructive node actions show
  "requires Admin".
- **Vault** node: lists *what* is configured and *when rotated* — never the value.
- **Runtime** node: public key + allowed origins + live/blocked state.
- **Guardrails** node: spend vs limit with warning / throttle / suspend bands; protected paths;
  approval gates. Red edge when suspended.

---

## 8. Interaction rules

1. **Wiring is automatic, not drawn.** Users configure nodes; edges appear. Not a flow builder.
2. **Inspect everything.** A node or edge click yields real data in the inspector.
3. **Gate the dangerous.** Write edges wear a shield; approval is a canvas action.
4. **Reduced motion is first-class.** A static mode renders coloured lines, no packets.
5. **Truth or nothing.** No green without a real successful call.

## 9. Phasing

1. **Graph home** — Brain + capability nodes, derived edge states, node inspector (this prototype).
2. **Live pulses** — drive packets from the SSE stream; per-edge health checks.
3. **Outliner + mode segment** — promote the graph into the app frame; retire the card grid.
4. **Guardrails, Vault, Runtime nodes** — full policy and access surfaces on the canvas.
