# MCP design and implementation

Standards for exposing Panthacloud's capabilities over the Model Context Protocol — the
"tailor and ship MCP servers" item in the product's use cases.

**No MCP code exists in this repository yet.** This is a design standard, written before the
first server, so that the first one is built to it.

Spec baseline: **MCP 2026-07-28** (current at 2026-10-12). Verified against
[modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2026-07-28).

## 1. What changed recently, and why it matters

Two revisions matter for anyone starting now:

- **2025-11-25** replaced the HTTP+SSE transport with **Streamable HTTP**, and added an
  **OAuth 2.1** authorization framework. Do not implement against the older HTTP+SSE transport.
- **2026-07-28** makes the core **stateless**. Session state is dropped, which is what allows
  horizontal scaling and ordinary HTTP infrastructure in front of a server.

Starting on 2026-07-28 means no session store, no sticky routing, and a server that scales like
any other HTTP service.

## 2. MCP or REST?

MCP is a different thing from the REST API, not a replacement for it. Both are correct, for
different consumers.

| | REST (`/api/v1/**`) | MCP |
|---|---|---|
| Consumer | Our own Studio, integrations, anything with a token | An LLM client discovering what exists |
| Discovery | You write the client | `tools/list`, `resources/list` |
| Shape | Fixed, versioned, documented | Self-describing at runtime |
| Auth | Our bearer tokens | OAuth 2.1 per the spec |

**Ship both.** The REST API stays the contract for software. MCP is what lets a customer plug
their existing assistant into their business without us writing an integration for it — which is
exactly the "MCP server tailoring and shipping" line in the nav.

## 3. Mapping our concepts onto MCP primitives

| Panthacloud | MCP primitive | Notes |
|---|---|---|
| A tool (`app/tools/`) | **Tool** | Executable, has side effects, model-invoked |
| Knowledge document | **Resource** | Read-only, addressed by URI |
| A saved prompt / persona | **Prompt** | Templated text, user-invoked |
| The assistant itself | **Server** | One capability boundary |

The distinction that matters: **tools do things, resources are things.** If a capability only
reads, it is a resource. Exposing reads as tools wastes a round trip and loses caching.

## 4. Resources need URIs

Resources are addressed by URI, and the URI scheme is ours to define:

```
pc://organizations/{org_id}/projects/{project_id}/documents/{document_id}
pc://organizations/{org_id}/knowledge
```

Rules:

- **Stable.** Changing a URI breaks a client's stored references.
- **Readable without a lookup.** The client should not need to fetch something to interpret it.
- **Never carry a secret.** A bearer token in a URI ends up in logs.

## 5. Transport

**Streamable HTTP** only. One endpoint, POST for messages, GET for the server-to-client stream.
Do not implement HTTP+SSE — it is the superseded transport.

```
POST /mcp          JSON-RPC 2.0 messages
GET  /mcp          server-initiated stream
```

JSON-RPC 2.0 is the wire format: `jsonrpc: "2.0"`, `id` on requests, `result` or `error` on
responses. Batch where it helps, but never assume a client can handle it.

## 6. Authorization

Per the 2025-11-25 revision, MCP authorization is **OAuth 2.1**, and it is at the transport
level.

- Authorization is **optional** per server. A public server may omit it.
- When present it is **OAuth 2.1**, not OAuth 2.0 with a password grant.
- Resource Indicators (RFC 8707) bind the token to the audience — otherwise a token issued for
  one server is replayable against another.
- **Every tenant is a resource server.** A token scopes to one organization. A token that can
  read organization A must not read organization B.

This is the same multi-tenant boundary the REST API already enforces by path. MCP moves the
boundary into the token, so the check moves with it rather than disappearing.

## 7. Security

MCP servers are agent-reachable, which means an agent can be induced to call them with hostile
arguments. Treat every call as untrusted input.

- **Validate every argument against the tool's Pydantic schema**, before any handler runs.
- **Never execute tenant code** as a side effect of a tool call. This is ASI05 and it holds for
  MCP exactly as it holds internally.
- **Capabilities are per-tenant and opt-in.** A server exposing `write_file` is a much larger
  commitment than one exposing `read_file`. Ship the smallest useful capability set.
- **Visible side effects need approval**, recorded with a provenance, as in `tool-design.md`.
  A PR opened through MCP is still a PR a person can see.
- **Rate-limit per tenant and per token**, not globally.

## 8. Naming and descriptions

Everything in `tool-design.md` applies unchanged — MCP tools are the same tools, described for
a client that may be another vendor's assistant.

- `snake_case` tool names, verb-first, one job.
- Descriptions carry what/when/what-not, because the descriptions ship inside
  `tools/list` and are often the only thing the other side reads.
- Structured content returns, not prose, where the spec supports it.

## 9. Versioning

Pin the protocol version in the server's `initialize` response and refuse versions you do not
implement rather than negotiating loosely.

The model-facing surface — tool names and schemas — follows the same compatibility rule as the
REST API: adding an optional field is not breaking; removing or renaming one is.

## 10. Checklist for a new MCP server

1. Is this genuinely MCP, or would a documented REST endpoint serve the consumer better?
2. Protocol 2026-07-28. Streamable HTTP. Stateless core.
3. Reads are resources; actions are tools. Do not expose reads as tools.
4. Resource URIs are stable, readable and secret-free.
5. Every argument validated against the tool schema before the handler.
6. Authorization per the spec, or explicitly documented as absent.
7. Tokens scoped to one tenant, with resource indicators.
8. Side-effecting tools gated by approval with recorded provenance.
9. Smallest capability set that is useful.
10. Descriptions written for a reader who has never seen this codebase.
11. Rate limits per tenant.
12. Protocol version pinned and unsupported versions refused.

## 11. Sources

- [MCP specification, current revision](https://modelcontextprotocol.io/specification/2026-07-28)
- [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) ·
  [Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources) ·
  [Prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)
- [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [Authorization changes in 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [JSON-RPC 2.0](https://www.jsonrpc.org/specification)
- [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- See also `tool-design.md` and `api-routing-standards.md`.