import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.repository import RepositoryProvider, RepositoryStatus


class RepositoryBase(BaseModel):
    provider: RepositoryProvider
    name: str = Field(..., min_length=1, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    external_id: str = Field(..., min_length=1, max_length=255)
    default_branch: str = Field("main", min_length=1, max_length=255)
    url: str | None = Field(None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepositoryCreate(RepositoryBase):
    integration_id: uuid.UUID
    status: RepositoryStatus = RepositoryStatus.PENDING


class RepositoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    full_name: str | None = Field(None, min_length=1, max_length=255)
    default_branch: str | None = Field(None, min_length=1, max_length=255)
    url: str | None = Field(None, max_length=512)
    status: RepositoryStatus | None = None
    metadata: dict[str, Any] | None = None


class RepositoryRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    integration_id: uuid.UUID
    provider: RepositoryProvider
    name: str
    full_name: str
    external_id: str
    default_branch: str
    url: str | None = None
    status: RepositoryStatus
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
