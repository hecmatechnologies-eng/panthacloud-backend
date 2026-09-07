# Fussion — Reference Architecture (Phases 1–27 Summary)

This document provides the authoritative architectural synthesis derived from Design Phases 1–27.

---

## 1. System Vision

Fussion is an **AI Integration Engineer Platform**. Rather than providing a simplistic embed script, Fussion acts as an automated software engineer:
1. It connects to a business's website repository and company knowledge base.
2. It analyzes the frontend framework, styling, and application shell.
3. It generates an integration plan and requests human approval.
4. It implements, styles, tests, and verifies a branded AI assistant in an isolated sandbox.
5. It produces a pull request and orchestrates preview and production deployment.

---

## 2. Layered Architecture

```text
                           FUSSION
                              │
         ┌────────────────────┴────────────────────┐
         │                                         │
   CONTROL PLANE                              DATA PLANE
         │                                         │
  Identity / IAM                            Website Widget
  Tenant / Policy                           Runtime API
  Projects / Jobs                           Runtime Agents
  Approvals                                 Knowledge / RAG
  Billing / Usage                           Streaming
         │                                         │
         └────────────────────┬────────────────────┘
                              │
                        ORCHESTRATION
                              │
                        AGENT HARNESS
                              │
                     ┌────────┴────────┐
                     │                 │
                   AGENTS            GUARDS
                     │                 │
                     └────────┬────────┘
                              │
                          TOOL / MCP
                              │
                     ┌────────┴────────┐
                     │                 │
                  SANDBOX        EXTERNAL APIS
                     │
               CUSTOMER CODE
                     │
                  PREVIEW
                     │
                 APPROVAL
                     │
                PRODUCTION
```

---

## 3. Core Planes & Boundaries

### Control Plane
- Authoritative administrative security boundary.
- Manages users, organizations (businesses), memberships, projects, policies, approvals, and secret configurations.

### Orchestration & State Machine
- Deterministic orchestrator coordinates engineering agents.
- Enforces state transitions: `CREATED` → `ANALYZING` → `PLANNING` → `WAITING_FOR_APPROVAL` → `IMPLEMENTING` → `TESTING` → `REPAIRING` → `PREVIEWING` → `READY_FOR_DEPLOYMENT` → `DEPLOYING` → `COMPLETED`.
- LLMs never own authoritative workflow state.

### Agent Harness & Security
- The harness controls LLM inputs, system prompts, capability tokens, and output parsing.
- Capabilities are narrow (e.g. `repo:read`, `sandbox:execute`, `deploy:preview`).
- LLMs are NEVER given raw GitHub tokens or master database credentials.

### Execution Sandbox
- Isolated worker environment for build, test, and dependency-install operations.
- Direct execution on the control plane server is strictly forbidden.

### Data Plane & Runtime
- Serves website visitors interacting with deployed assistants.
- Isolated from engineering planes: runtime agents have NO write access to repositories or deployment credentials.
