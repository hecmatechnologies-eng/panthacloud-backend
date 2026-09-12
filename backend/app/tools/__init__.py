"""Tool layer: the agent's entire interface to the world, behind one gateway (AGENT-ARCHITECTURE §10).

Most agent failures in practice are tool failures. Tools here are few, unambiguous, typed read or
write, and written for the model. This is also the layer permitted to touch domain services, the
database, GitHub and the filesystem (CLAUDE.md §5).
"""
