# Third-party review: "Panthacloud Master Architecture Blueprint"

**Reviewed:** 2026-10-15 · **Source:** AI-generated, pasted from chat
**Verdict:** Do not adopt. It is internally incoherent, contradicts two ADRs accepted this
session, and its code does not run.

---

## 0. The headline problem

The blueprint describes a **different product**. It is not a redesign of Panthacloud; it is a
generic omnichannel CRM generated from the platform names. Read against the actual repository,
roughly half of it contradicts code that exists, works, and is under test.

The most concrete proof: **it deletes the `Project` layer.** Its `organizations` table holds
tenants directly, with no projects. In the real system `Project` owns `KnowledgeBase`,
`Assistant`, `WebsiteIntegration` and `Repository` — it is not a convenience, it is the thing that
scopes every query. A blueprint that drops it has not read the schema it is replacing.

---

## 1. Claims that are false against primary sources

**TikTok regional access — self-contradictory.** The blueprint says the API is blocked for
businesses registered in the United States. TikTok's own documentation says
*"TikTok Business Messaging API is now in Open Beta in APAC, LATAM, METAP, and North America."*
Both cannot be true. This needs checking against TikTok's regional access page before anyone plans
around it — I flagged this as unresolved last turn and the blueprint has not resolved it, only
replaced it with a different answer.

**The "10 messages / 48-hour threshold" is attributed to TikTok.** That resembles WhatsApp's
24-hour customer-service window, not a TikTok rule. Unverified, and stated as fact.

**Instagram's 24-hour session window and 7-day human-agent tag are correct.** Credit where due.

---

## 2. Security defects in the proposed design

### 2.1 The model chooses which tenant to send as — the critical one

```python
@mcp.tool()
def send_omnichannel_reply(organization_id: str, channel: str, ...):
    credentials = fetch_tenant_credentials(organization_id, channel)
```

`organization_id` is **supplied by the model**. Any prompt injection — from a knowledge document,
a visitor message, a webhook payload — can redirect this call at another tenant's credentials and
its token comes back in the tool result.

This inverts the central safety property of the existing system. Tenant scoping is currently
*structural*: the organisation id is in the URL path, `get_current_organization` resolves membership
and returns **404 rather than 403** to prevent enumeration, and `ToolGateway` re-asserts
`run.organization_id == context.organization_id` at the tool layer. Three independent places a
request cannot cross a tenant boundary.

The blueprint collapses all three into a string the model controls. This is LLM06/LLM01 territory
and it is the single most dangerous thing in the document.

**Rule, for any version of this:** the tenant comes from the *server-side session*, never from a
tool argument.

### 2.2 The WhatsApp webhook is unauthenticated

`handle_tiktok_webhook` is signature-checked. `handle_whatsapp_webhook` is **not** — no
`X-Hub-Signature-256` HMAC, no verification. Anyone who can POST to that URL can make the business
receive messages. That is an open relay into a paying customer's inbox.

Meta requires the HMAC handshake. The omission looks like an oversight, not a decision.

### 2.3 The widget webhook has no authentication at all

```python
@app.post("/webhooks/widget/{organization_id}")
async def handle_widget_webhook(organization_id: str, payload: Dict[str, Any]):
```

Anyone can POST as any organisation. The organisation id is taken from the URL and trusted.

### 2.4 Credentials stored in plaintext, with a comment claiming otherwise

`access_token TEXT NOT NULL,  -- Encrypted permanent token` stores it unencrypted.

The existing system already has this: `SECRET_ENCRYPTION_KEY` is required in production,
`effective_secret_encryption_key()` refuses to start without it, and `Integration.encrypted_secrets`
is the column. The blueprint deletes working encryption and replaces it with a comment.

---

## 3. What it would delete

| Blueprint | Reality | Consequence |
|---|---|---|
| `guest_sessions`, `session_messages` | `VisitorSession`, `Conversation`, `Message` | drops `citations`, `assistant_version`, `prompt_hash` — **the provenance the runtime eval corpus pins** |
| *(absent)* | `model_usage` | the entire spend ledger; budgets stop being measurable |
| *(absent)* | `memberships`, `RoleEnum` | **no roles at all**; every tenant user is equivalent |
| *(absent)* | `projects` | the scoping layer for KB, Assistant, Integration, Repository |
| `agent_configs.persona_prompt` + `business_goal` | `Assistant.system_instructions` | splits an append-only field into two editable ones that can conflict |
| *(absent)* | gateway budgets, 4-tier rate limits | cost and abuse protection gone |

---

## 4. Contradicts two ADRs accepted this session

**ADR-003 rejected MCP before it was needed**, citing a measured 78.3% attack success rate with
five MCP servers attached to one agent. Its revisit trigger is *third-party-authored tools*.

**But the decisive objection is simpler: the MCP server is not needed for this job.** Its stated
purpose is "take a channel, fetch credentials, send." That is an outbound dispatcher — a function
call. Wrapping it in MCP adds a process boundary, a network hop, a serialisation layer, and an
attack surface, and buys nothing. MCP exists so *tenants* can attach their own tools. Your own
first-party send path should be a function behind the existing `ModelProvider` seam, which was
built for exactly this.

**ADR-004 says channel adapters must reach the model through `handle_chat`** so they inherit the
outbound guard and the budget. The blueprint's three-service split puts the MCP server and the
webhook router on their own database connections, outside that path. The guardrail built this
session — the lagged stream guard, the asymmetric PII redaction — would not run.

It also breaks streaming. The widget's SSE response cannot survive a split between the orchestrator
and the sender.

---

## 5. The code does not run

Verified by reading, not by assumption:

- `if name == "main":` — missing underscores. Every execution path in both Python blocks is dead.
- Indentation destroyed across both files — `try`/`except` bodies at the wrong level throughout.
- `url = f"facebook.com{account_id}/messages"` — not a URL. Missing `https://api.graph.facebook.com/v21.0/`.
- `url = "tiktok.com"` — not a URL at all.
- `js.src = "facebook.net"` — not a URL.
- `Authorization: Bearer ${...}` — a template literal missing its backticks; the fetch would not parse.
- `except Exception: return {}` — swallows every failure including a dropped database, returning
  "no credentials" and silently reporting a routing failure.
- Tool results return raw provider error text into model context.

A blueprint whose code has `if name == "main"` has not been executed. That is worth weighing before
its architecture is considered.

---

## 6. What is genuinely worth keeping

Not everything here is wrong, and two items are better than anything in the current system.

**Self-loop prevention on TikTok.** `if content_data.get("source") == "API"` guards against the
agent's own outbound messages re-entering as inbound input and looping. That is a real, non-obvious
platform hazard and it is not in the ADR set.

**Meta Embedded Signup for onboarding.** Letting a tenant authorise their own WhatsApp account from
the dashboard removes per-tenant manual configuration entirely. `OAuth → session_code → backend`
is the correct shape, and it is a genuine product improvement the current system does not have.

**Normalising to one inbound shape.** Correct in principle — though `app/channels/base.py` already
exists for it, written to the same idea with the failure modes (idempotency, group addressing,
identity normalisation) already pinned by tests.

---

## 7. Recommendation

**Reject the blueprint as an architecture. Harvest two ideas from it.**

1. Take **self-loop prevention** into the channel contract as a test.
2. Take **Meta Embedded Signup** into the onboarding plan — it is a real product win.
3. Take the **verification-handshake and per-channel window** items into `app/channels/` as
   documented provider constraints.

Keep everything already built. Specifically, nothing here justifies replacing the `ModelProvider`
seam, the tenancy chain, the spend ledger, provenance, or the guardrails.

If omnichannel is genuinely the next priority, the correct next slice is still the one already
planned: **nullable `integration_id` on `VisitorSession` plus a channel discriminator.** That is
about forty lines and it unblocks every adapter. A three-microservice split is a later decision,
taken when there is load that justifies it — not written down in advance by a generator.