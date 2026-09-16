"""The resolved composition of a project — the context an agent runs against.

This is **Option A** of the workspace design: a *resolver*, not a table. Everything here is derived
from rows that already exist, so there is nothing to keep in sync and nothing to migrate. It exists
so the agent layer has one object that answers two questions in one place:

    1. What is this project made of? (assistant, knowledge, repository)
    2. Is every part of it the same organization? (the tenancy proof)

Not to be confused with ``app.services.repository.workspace``, which is the per-run *filesystem*
sandbox. This is the logical workspace; that is the physical one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# Component kinds a project can have. Presence is derived, never stored.
ASSISTANT = "assistant"
KNOWLEDGE = "knowledge"
REPOSITORY = "repository"


@dataclass(frozen=True, slots=True)
class ModelBinding:
    """The model a workspace's agents run on.

    Deployment-scoped today: one gateway is configured per process (``app.llm.factory``). A
    per-organization override would need its own table, which is deliberately not introduced until
    something actually requires it.
    """

    provider: str
    model_id: str
    configured: bool


@dataclass(frozen=True, slots=True)
class ProjectWorkspace:
    """A project's resolved components and runtime bindings, frozen once resolved.

    Carries identifiers and facts, never credentials: the GitHub token is resolved per call by the
    tool layer (CLAUDE.md §4.2), and the model binding describes *which* model, not how to reach it.
    """

    organization_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    assistant_id: uuid.UUID | None
    assistant_enabled: bool
    knowledge_base_id: uuid.UUID | None
    knowledge_document_count: int
    integration_id: uuid.UUID | None
    repository: str | None
    default_branch: str | None
    github_installation_id: int | None
    model: ModelBinding

    @property
    def components(self) -> frozenset[str]:
        """Which components this project actually has. An agent may only use these."""
        present: set[str] = set()
        if self.assistant_id is not None:
            present.add(ASSISTANT)
        if self.knowledge_base_id is not None:
            present.add(KNOWLEDGE)
        if self.integration_id is not None:
            present.add(REPOSITORY)
        return frozenset(present)


class WorkspaceIntegrityError(RuntimeError):
    """A component resolved for a workspace does not belong to the workspace's organization.

    A tenancy violation, not a missing record. It fails closed rather than serving a mixed context:
    an agent must never be handed a credential or a resource from another tenant.
    """
