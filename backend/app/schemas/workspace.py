"""Read model for a project's resolved workspace.

The workspace is a resolver, not a table (docs in ``app.services.project_workspace``), so this
schema is a projection of it, not an ORM mapping.
"""

import uuid

from pydantic import BaseModel

from app.services.project_workspace.models import ProjectWorkspace


class ModelBindingRead(BaseModel):
    provider: str
    model_id: str
    configured: bool


class ProjectWorkspaceRead(BaseModel):
    organization_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    # Which components exist, so a client can show the project's real composition.
    components: list[str]
    assistant_id: uuid.UUID | None
    assistant_enabled: bool
    knowledge_base_id: uuid.UUID | None
    knowledge_document_count: int
    integration_id: uuid.UUID | None
    repository: str | None
    default_branch: str | None
    github_installation_id: int | None
    model: ModelBindingRead

    @classmethod
    def from_workspace(cls, workspace: ProjectWorkspace) -> "ProjectWorkspaceRead":
        return cls(
            organization_id=workspace.organization_id,
            project_id=workspace.project_id,
            project_name=workspace.project_name,
            components=sorted(workspace.components),
            assistant_id=workspace.assistant_id,
            assistant_enabled=workspace.assistant_enabled,
            knowledge_base_id=workspace.knowledge_base_id,
            knowledge_document_count=workspace.knowledge_document_count,
            integration_id=workspace.integration_id,
            repository=workspace.repository,
            default_branch=workspace.default_branch,
            github_installation_id=workspace.github_installation_id,
            model=ModelBindingRead(
                provider=workspace.model.provider,
                model_id=workspace.model.model_id,
                configured=workspace.model.configured,
            ),
        )
