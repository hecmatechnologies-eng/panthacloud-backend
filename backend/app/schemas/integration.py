import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.integration import IntegrationProvider, IntegrationStatus


class IntegrationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider: IntegrationProvider
    configuration: dict[str, Any] = Field(default_factory=dict)


class IntegrationCreate(IntegrationBase):
    secrets: dict[str, str] | None = Field(
        None,
        description="Optional credentials/secrets to be encrypted into secret store; never returned in responses.",
    )
    status: IntegrationStatus = IntegrationStatus.PENDING


class IntegrationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    configuration: dict[str, Any] | None = None
    secrets: dict[str, str] | None = Field(
        None,
        description="Updated credentials/secrets to be encrypted into secret store.",
    )
    status: IntegrationStatus | None = None


class IntegrationRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    provider: IntegrationProvider
    name: str
    status: IntegrationStatus
    configuration: dict[str, Any]
    has_credentials: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
