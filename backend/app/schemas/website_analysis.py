"""Website analysis read model (step C10)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WebsiteAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    integration_id: uuid.UUID
    commit_sha: str
    framework_skill_id: str | None = None
    router: str | None = None
    language: str | None = None
    package_manager: str | None = None
    build_command: str | None = None
    entry_points: list[str] = []
    integration_candidates: list[dict[str, Any]] = []
    design_tokens: dict[str, Any] = {}
    protected_paths: list[str] = []
    unsupported_reason: str | None = None
    created_at: datetime


class AnalysisJobResponse(BaseModel):
    """Response returned when an analysis job is enqueued asynchronously (HTTP 202)."""

    status: str
    job_id: str
    poll_url: str
    events_url: str
