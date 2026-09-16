# Step B — Runtime Plane, sliced

Step B from `docs/FEASIBILITY.md` §3, broken into slices. Propose no work outside the
current slice. Each slice declares its rigour tier per `CLAUDE.md` §9.0.

| # | Slice | Tier | Done when |
|---|---|---|---|
| B1 | Public key + `AllowedOrigin` model + migration + management endpoints | 2 | An integration has a public key and registered origins. No behaviour yet. |
| B2 | Tenant resolver | 1 | A function turns `public_key` + `Origin` into a trusted `TenantContext`, or refuses. Cross-tenant combinations fail. Unknown key and unregistered origin return identical responses. |
| B3 | `VisitorSession`, `Conversation`, `Message` + migration | 2 | Schema exists with retention fields. Nothing writes to it yet. |
| B4 | Public chat endpoint — **no model** | 1 | A real public endpoint, correctly tenanted, rate-limited, persisting messages, returning a canned reply. |
| B5 | `ModelProvider` + `ModelGateway` | 1 | The widget gets a real LLM answer. Budgets, caps, timeouts and usage records all enforced at the gateway. |
| B6 | Real embeddings + tenant-filtered retrieval | 1 | Answers are grounded in the business's own documents, with citations. Embedding dimension lives on the `KnowledgeBase`, not the call site. |
| B7 | SSE streaming | 2 | Tokens appear as they generate; keepalive and reconnection contract defined. |
| B8 | Real widget — Shadow DOM, working chat panel | 1 | The MVP promise is demonstrable end to end on a real site. |
| B9 | `CustomerAssistant` declaration — the runtime's counterpart of `AgentDefinition` | 2 | Instructions, capabilities, tools and limits are declared once in `app/runtime/assistant.py` and resolved from the tenant's configuration. The platform's grounding layer is always present; a tenant's instructions extend it and never replace it. A capability or tool the runtime does not have is refused at construction. |
| B10 | Per-organization model selection — `organization_model_settings`, resolver, endpoint, runtime wiring | 1 | An organization may choose any model on the deployment's allow-list, or clear the choice back to the default. The choice reaches the runtime's model call, not just the settings screen. `ORG_UPDATE` (OWNER, ADMIN) governs it; any member may read it. |

## Notes

**B4 precedes B5 deliberately.** Build the public surface and prove it is correctly
tenanted and rate-limited *before* a model sits behind it. Getting tenancy wrong with a
canned response costs nothing; getting it wrong with a model behind it means one tenant's
data in another tenant's chat window. It also yields a shippable, testable public endpoint
roughly a week earlier.

**pgvector is not a Step B slice.** Full-scan cosine is adequate at a few hundred chunks.
Make it its own slice when volume demands it — `CLAUDE.md` §6, Avoid Premature
Optimization.

**B8's widget code is needed regardless of how it is emitted.** A template emits it today;
a skill package will emit it after Step D. Keep the widget source independent of
`artifacts.py`, which is scheduled for replacement per AGENT-ARCHITECTURE §6.
