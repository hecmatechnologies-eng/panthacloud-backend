"""Model plane: the single seam between Fussion and any model vendor (FR-072, FR-125).

Concrete providers — and any vendor SDK they use — live in ``app/llm/providers/``. Nothing in
``app/agents/``, ``app/harness/`` or ``app/runtime/`` imports a vendor SDK directly.
"""
