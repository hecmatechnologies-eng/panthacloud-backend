"""Agent layer: thin, declarative definitions only (AGENT-ARCHITECTURE §3).

An agent declares what it is — name, version, instructions, capabilities, tools, output schema and
budget. It holds no infrastructure: no SQLAlchemy, no httpx, no domain service. The harness runs it.
"""
