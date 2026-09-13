import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.origins import MAX_ORIGIN_LENGTH, normalize_origin
from app.core.target_paths import unsafe_target_reason
from app.models.website_integration import (
    DEFAULT_FRAMEWORK_SKILL_ID,
    KNOWN_FRAMEWORK_SKILL_IDS,
    IntegrationRunStatus,
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
    framework_skill_id: str
    website_root_dir: str
    widget_target_path: str
    status: WebsiteIntegrationStatus
    has_credentials: bool = False
    github_installation_id: int | None = None
    public_key: str
    last_error: str | None = None
    last_success_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


def _reject_unsafe_target(path: str | None) -> str | None:
    """Refuse an unsafe widget target at configuration time (FR-096, step C11).

    The earliest gate: without it the user saves a configuration, `GET /plan` renders a plan
    promising to modify `.github/workflows/deploy.yml`, and only the run — at the end — says no.
    It applies the same checks the analyst's target selection does (`app.core.target_paths`), so a
    path is safe however it was chosen — typed, or selected from the analyst's candidates.
    """
    if path is None:
        return None
    reason = unsafe_target_reason(path)
    if reason:
        raise ValueError(
            f"'{path}' cannot be the widget target ({reason}). Fussion writes only to the "
            "application shell, such as app/layout.tsx or index.html."
        )
    return path.strip()


def _reject_unknown_framework_skill(skill_id: str | None) -> str | None:
    """Refuse an unknown skill id at configuration time (FR-082).

    The stored value is a free string, but only ids the generator can build are meaningful: an
    unknown one would reach the planner and yield a plan with no files instead of an error.
    """
    if skill_id is not None and skill_id not in KNOWN_FRAMEWORK_SKILL_IDS:
        raise ValueError(
            f"Unknown framework skill id '{skill_id}'. Known ids: "
            f"{', '.join(sorted(KNOWN_FRAMEWORK_SKILL_IDS))}."
        )
    return skill_id


class WebsiteIntegrationCreate(BaseModel):
    repository_owner: str = Field(..., min_length=1, max_length=255)
    repository_name: str = Field(..., min_length=1, max_length=255)
    default_branch: str = Field("main", min_length=1, max_length=100)
    framework_skill_id: str = Field(DEFAULT_FRAMEWORK_SKILL_ID, max_length=100)
    website_root_dir: str = Field("/", max_length=255)
    widget_target_path: str = Field("app/layout.tsx", max_length=255)
    github_token: str | None = Field(None, max_length=500)
    # Set when connected through the GitHub App; then no token is needed. Validated to belong to
    # the caller's organization by the endpoint.
    github_installation_id: int | None = None

    _check_target = field_validator("widget_target_path")(_reject_unsafe_target)
    _check_skill = field_validator("framework_skill_id")(_reject_unknown_framework_skill)


class WebsiteIntegrationUpdate(BaseModel):
    repository_owner: str | None = Field(None, min_length=1, max_length=255)
    repository_name: str | None = Field(None, min_length=1, max_length=255)
    default_branch: str | None = Field(None, min_length=1, max_length=100)
    framework_skill_id: str | None = Field(None, max_length=100)
    website_root_dir: str | None = Field(None, max_length=255)
    widget_target_path: str | None = Field(None, max_length=255)
    github_token: str | None = Field(None, max_length=500)

    _check_target = field_validator("widget_target_path")(_reject_unsafe_target)
    _check_skill = field_validator("framework_skill_id")(_reject_unknown_framework_skill)


class AllowedOriginCreate(BaseModel):
    # Bounds the raw input; normalize_origin enforces the stored length after trimming.
    origin: str = Field(..., max_length=2 * MAX_ORIGIN_LENGTH)

    @field_validator("origin")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_origin(value)


class AllowedOriginRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    origin: str
    created_at: datetime


# Whether the widget target file was confirmed in the repository before planning.
TargetStatus = Literal["exists", "missing", "unknown"]


class IntegrationPlanPayload(BaseModel):
    framework_skill_id: str
    files_to_create: list[str]
    files_to_modify: list[str]
    files_to_delete: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str | None = None
    target_status: TargetStatus = "unknown"


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
    framework_skill_id: str
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
