"""``ExecutionContext`` — the tenancy carrier (FR-048, FR-049).

The most important object in the agent layer. Constructed by trusted infrastructure from server
state — never from, or modified by, model output. Every tool call and every query resolves its
scope from it, so an agent cannot name a tenant, a repository, or a capability it was not granted.

Frozen: once built, a stage cannot widen its own scope. ``bind_run`` returns a new context, which is
how the run id is attached after the ``AgentRun`` row exists.
"""

import uuid
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    organization_id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID | None
    environment: str
    agent_name: str
    agent_version: str
    capabilities: frozenset[str]
    # The pinned revision the agent reads at. Present from C2 so C4's tools can read a commit,
    # rather than widening every call site later.
    commit_sha: str | None = None
    agent_run_id: uuid.UUID | None = None

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def bind_run(self, agent_run_id: uuid.UUID) -> "ExecutionContext":
        return replace(self, agent_run_id=agent_run_id)

    def snapshot(self) -> dict[str, Any]:
        """A JSON-serializable record for the ``AgentRun``, for audit and reproducibility."""
        return {
            "organization_id": str(self.organization_id),
            "project_id": str(self.project_id),
            "repository_id": str(self.repository_id) if self.repository_id else None,
            "environment": self.environment,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "capabilities": sorted(self.capabilities),
            "commit_sha": self.commit_sha,
            "agent_run_id": str(self.agent_run_id) if self.agent_run_id else None,
        }
