"""Project workspace — the resolved composition of a project (Option A: resolver, not a table)."""

from app.services.project_workspace.models import (
    ASSISTANT,
    KNOWLEDGE,
    REPOSITORY,
    ModelBinding,
    ProjectWorkspace,
    WorkspaceIntegrityError,
)
from app.services.project_workspace.resolver import resolve_project_workspace

__all__ = [
    "ASSISTANT",
    "KNOWLEDGE",
    "REPOSITORY",
    "ModelBinding",
    "ProjectWorkspace",
    "WorkspaceIntegrityError",
    "resolve_project_workspace",
]
