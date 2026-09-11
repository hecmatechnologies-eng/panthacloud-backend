import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.repository_snapshot import SnapshotStatus


class SnapshotCreate(BaseModel):
    branch: str = Field("main", min_length=1, max_length=255)


class SnapshotRead(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    branch: str
    commit_sha: str | None = None
    status: SnapshotStatus
    acquired_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StructureInfo(BaseModel):
    file_count: int
    directory_count: int
    total_size_bytes: int
    maximum_depth: int


class RepositoryInfo(BaseModel):
    name: str
    default_branch: str


class InspectionResult(BaseModel):
    snapshot_id: uuid.UUID
    commit_sha: str | None = None
    repository: RepositoryInfo
    structure: StructureInfo
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    manifests: list[str] = Field(default_factory=list)
    api_contracts: list[str] = Field(default_factory=list)
    deployment_files: list[str] = Field(default_factory=list)
