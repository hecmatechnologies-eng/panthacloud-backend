"""Adapters behind Fussion's own Protocols (ADR-001, FR-125).

`pydantic_ai` is imported only in this package — never in `app/agents/`, `app/harness/`,
`app/tools/` or `app/runtime/`. Everything here is swappable by replacing a file.
"""
