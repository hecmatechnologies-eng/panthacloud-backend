# Tool design and implementation

Standards for the tools the agents call. These are the only surface a model interacts with
directly, so their shape decides whether an agent is reliable or merely plausible.

Applies to `backend/app/tools/`. Current state: `base.py` (the contract), `gateway.py` (the
single execution path), `registry.py`, `repository.py`, `workspace.py`.

## 1. The shape of a tool

Every tool is a named, described, schema-validated function:

```python
read_tree = Tool(
    name="read_tree",
    description="List the files and directories at a path in the connected repository.",
    input_schema=ReadTreeArgs,     # a Pydantic model
    handler=_read_tree,
)
```

Two rules that are not negotiable:

- **The schema is a Pydantic model, not a dict.** Constraints (`ge`, `le`, `min_length`,
  `max_length`) are enforced before the handler runs, so a bad argument never reaches code that
  could be harmed by it.
- **Every field carries a description.** The model reads these, not the Python signature. A
  field with no description is a field the model will guess wrong about.

## 2. Naming

- **snake_case**, matching the wire format everywhere else.
- **Verb first, object second**: `read_tree`, `write_file`, `list_branches`. The model composes
  these; it does not read them.
- **Name the action, not the implementation.** `read_tree` survives a change from a git tree to
  an archive. `git_ls_tree` does not.
- **One tool, one job.** A tool that lists and also writes cannot be authorised, audited or
  explained in isolation.

## 3. Descriptions are the API

The description is the model's only documentation. It should state:

1. **What it does**, in one sentence, in the imperative.
2. **When to use it**, if another tool is a plausible alternative.
3. **What it does not do**, if that is a real trap.

```python
description=(
    "Read a file from the repository at a pinned commit. "
    "Use read_tree first to confirm the path exists. "
    "Does not follow paths outside the repository root."
)
```

Vague descriptions produce tools that get called in the wrong order, or not at all. This is the
most common failure mode and it is invisible in testing — the tests pass and the agent still
misbehaves.

## 4. Arguments

- **Every argument needs a `description`.**
- **Constrain everything.** An unbounded `limit` is a denial-of-service vector against our own
  context window.
- **Prefer enums over booleans.** `mode: Literal["read", "write"]` cannot be inverted by
  mistake; `overwrite: bool` can.
- **Sensible defaults, always.** A required argument the model must always supply is a chance
  to get it wrong.
- **No free-form paths without a boundary.** Paths are validated against the repository root.
  That check is a security control, not a convenience.

## 5. Return values

- **Return data, not prose.** The model reads structure far more reliably than sentences.
- **Be explicit about emptiness.** Return `[]` and `null`, never an empty string standing in
  for "nothing found".
- **Stay inside the context budget.** A tool that returns 50,000 lines has broken the agent,
  whatever it was asked to do. `read_file` defaults to 200 lines and caps at 2000 — that
  default is a design decision and should stay.

## 6. Side effects and approval

Not every tool may run freely. The gateway distinguishes:

- **Read-only** — safe to call without a gate.
- **Externally visible** — anything a person or another system will observe: opening a pull
  request, sending a message, committing to a branch.

This is the distinction behind `ASI05` and the approval model: **tenant code is never
executed, and an effect a person can see attaches an approval to the call, not to the run.** The
approval is recorded with its approver, so provenance survives.

Rules:

- A tool declares its class. The caller never overrides it.
- An approved call records who approved it and when. An approval with no provenance is not an
  approval.
- A refusal is a valid outcome with a reason. Never silently degrade to a partial write.

## 7. Everything goes through the gateway

`gateway.py` is the only execution path, and it does four things in order:

1. **Validates** arguments against the tool's schema.
2. **Records** the call — tool name, arguments, result, duration, cost.
3. **Redacts** secrets from arguments and results before either is persisted or returned.
4. **Applies** the circuit breaker and the kill switch.

A new tool must not be callable by importing its handler and calling it directly. That skips
all four, and in particular skips redaction.

## 8. Failure

- **Raise a typed error, never return an error string.** The model cannot reliably tell the
  difference between a result that says "failed" and a result that failed.
- **Errors carry a reason a model can act on.** "File not found at src/app.tsx; the closest
  match is src/app/page.tsx" is actionable. "Not found" is not.
- **One failure, one retry policy.** Transient and permanent failures are distinguished at the
  gateway, not guessed at by the model.

## 9. Determinism before the model

The existing rule, and the one that matters most: **framework detection, entry points and
insertion points are found by deterministic code.** The model is called only where code has
genuinely failed to decide. Every place the model is used to do something a parser could do is
a place where the tool boundary has been drawn in the wrong spot.

## 10. Testing a tool

- **Unit test the handler** with valid input and with each constraint violated.
- **Test through the gateway** for anything involving redaction, approval or the breaker.
- **Eval the description, not just the behaviour.** A tool whose description has drifted from
  what it does will keep "passing" its unit tests while agents stop calling it.

## 11. Checklist

1. `snake_case`, verb-first, one job.
2. Description says what it does, when to use it, and what it does not do.
3. Pydantic schema, every field described, every bound constrained.
4. Defaults chosen so the common case needs no argument.
5. Return structure, never prose.
6. Side-effect class declared at definition.
7. Handler unreachable except through `gateway.py`.
8. Typed errors with actionable reasons.
9. Redaction tested, not assumed.
10. Description eval exists alongside the unit tests.

## 12. Sources

- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/schema) — the shape tool schemas
  reduce to
- [Pydantic](https://docs.pydantic.dev/latest/) — constraint enforcement
- [Anthropic, writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
  — the wire format when these are exposed externally; see `mcp-design.md`
- See also `api-routing-standards.md` — a tool's HTTP surface follows the same rules as any
  other endpoint.