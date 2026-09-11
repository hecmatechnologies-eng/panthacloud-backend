import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.website_integration import (
    IntegrationRunStatus,
    WebsiteFramework,
    WebsiteIntegrationStatus,
)


class WebsiteIntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    provider: str
    repository_owner: str
    repository_name: str
    default_branch: str
    integration_branch: str | None = None
    framework: WebsiteFramework
    website_root_dir: str
    widget_target_path: str
    status: WebsiteIntegrationStatus
    has_credentials: bool = False
    last_error: str | None = None
    last_success_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebsiteIntegrationCreate(BaseModel):
    repository_owner: str = Field(..., min_length=1, max_length=255)
    repository_name: str = Field(..., min_length=1, max_length=255)
    default_branch: str = Field("main", min_length=1, max_length=100)
    framework: WebsiteFramework = WebsiteFramework.REACT_NEXTJS
    website_root_dir: str = Field("/", max_length=255)
    widget_target_path: str = Field("app/layout.tsx", max_length=255)
    github_token: str | None = Field(None, max_length=500)


class WebsiteIntegrationUpdate(BaseModel):
    repository_owner: str | None = Field(None, min_length=1, max_length=255)
    repository_name: str | None = Field(None, min_length=1, max_length=255)
    default_branch: str | None = Field(None, min_length=1, max_length=100)
    framework: WebsiteFramework | None = None
    website_root_dir: str | None = Field(None, max_length=255)
    widget_target_path: str | None = Field(None, max_length=255)
    github_token: str | None = Field(None, max_length=500)


class IntegrationPlanPayload(BaseModel):
    framework: WebsiteFramework
    files_to_create: list[str]
    files_to_modify: list[str]
    files_to_delete: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str | None = None


class IntegrationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    integration_id: uuid.UUID
    status: IntegrationRunStatus
    branch_name: str
    commit_sha: str | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    sandbox_ref: str
    plan_summary: dict[str, Any] = Field(default_factory=dict)
    generated_files_count: int = 0
    modified_files_count: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ValidationResultPayload(BaseModel):
    status: str
    is_valid: bool
    repository: str
    owner: str
    repo: str
    default_branch: str
    framework: WebsiteFramework
    assistant_readiness: bool
    knowledge_base_readiness: bool
    issues: list[str] = Field(default_factory=list)


class DiffFileItem(BaseModel):
    path: str
    action: str  # "create" | "modify" | "delete"
    diff: str


class RunDiffPayload(BaseModel):
    run_id: uuid.UUID
    files: list[DiffFileItem] = Field(default_factory=list)
    summary: str


class PullRequestInfo(BaseModel):
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    branch_name: str
    base_branch: str
    title: str
    status: str
