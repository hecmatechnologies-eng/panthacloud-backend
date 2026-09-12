"""Visitor data plane (AGENT-ARCHITECTURE §8).

`app/runtime/` is the high-volume, low-latency path: resolve tenant → retrieve → assemble →
stream. It does not run the agent loop and must not import `app/agents/` or engineering tools
(CLAUDE.md §5).
"""
