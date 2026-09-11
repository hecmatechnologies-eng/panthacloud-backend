import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.integration_plan import IntegrationPlanStatus


class IntegrationCandidate(BaseModel):
    name: str
    type: str  # "DATABASE", "CACHE", "PAYMENTS", "STORAGE", "MESSAGE_BROKER", "AUTHENTICATION", "EXTERNAL_API"
    source: str = "DETECTED"  # "DETECTED", "INFERRED"
    confidence: str = "HIGH"  # "HIGH", "MEDIUM", "LOW"
    description: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class RequiredCredential(BaseModel):
    name: str  # e.g. "DATABASE_URL", "STRIPE_API_KEY"
    type: str = "API_KEY"  # "CONNECTION_STRING", "API_KEY", "SECRET_KEY", "TOKEN", "PASSWORD"
    service: str | None = None
    required: bool = True
    sensitive: bool = True  # Always True for security
    description: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class UnresolvedQuestion(BaseModel):
    id: str
    category: str  # "SECURITY", "CONFIGURATION", "DATA_STORE", "INTEGRATION", "CONTRACT"
    question: str
    impact: str = "HIGH"  # "HIGH", "MEDIUM", "LOW"
    suggested_action: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class IntegrationPlanRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    snapshot_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    status: IntegrationPlanStatus
    candidates: list[IntegrationCandidate] = Field(default_factory=list)
    required_credentials: list[RequiredCredential] = Field(default_factory=list)
    unresolved_questions: list[UnresolvedQuestion] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationPlanCreate(BaseModel):
    contract_id: uuid.UUID | None = None
