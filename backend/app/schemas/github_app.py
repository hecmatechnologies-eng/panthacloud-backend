"""GitHub App read models (step E1)."""

import uuid

from pydantic import BaseModel, ConfigDict


class GitHubInstallUrlRead(BaseModel):
    url: str


class GitHubInstallationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    installation_id: int
    account_login: str
    account_type: str
    repository_selection: str


class GitHubRepositoryRead(BaseModel):
    full_name: str
    name: str
    owner: str | None = None
    private: bool
    default_branch: str
    # The installation that grants access; the picker links the integration to it.
    installation_id: int


class GitHubRepositoryList(BaseModel):
    total_count: int
    repositories: list[GitHubRepositoryRead]
    page: int
    per_page: int
