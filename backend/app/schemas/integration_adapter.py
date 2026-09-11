import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.integration_adapter import AdapterStatus, AdapterType


class AdapterOperation(BaseModel):
    name: str = Field(..., description="Operation identifier (e.g. query_records, create_charge)")
    operation_type: str = Field(..., description="Type category of operation (QUERY, WRITE, SEND, RECEIVE, AUTHENTICATE)")
    method: str | None = Field(default=None, description="HTTP method if applicable")
    target: str = Field(..., description="Declarative target resource or operation namespace (never executable commands)")
    description: str | None = Field(default=None, description="Human-readable description of what this operation performs")
    source: str = Field(default="INFERRED", description="Origin of this mapping: DETECTED, INFERRED, or UNKNOWN")
    evidence: dict[str, Any] | list[Any] = Field(default_factory=dict, description="Evidence references linking to discovery or contract files")
    requires_approval: bool = Field(default=False, description="Whether this operation alters state and requires human approval")


class AdapterConfiguration(BaseModel):
    key: str = Field(..., description="Configuration variable name (e.g. DATABASE_URL, STRIPE_SECRET_KEY)")
    category: str = Field(..., description="Configuration category (e.g. DATABASE, PAYMENTS, AUTH)")
    required: bool = Field(default=True, description="Whether this configuration key is mandatory")
    description: str | None = Field(default=None, description="Description of the configuration requirement")
    evidence: dict[str, Any] | list[Any] = Field(default_factory=dict, description="Evidence files indicating configuration requirement")


class IntegrationAdapterCreate(BaseModel):
    integration_plan_id: uuid.UUID | None = Field(default=None, description="Optional explicit integration plan ID to generate adapters from")


class IntegrationAdapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    integration_plan_id: uuid.UUID
    snapshot_id: uuid.UUID
    name: str
    adapter_type: AdapterType
    provider: str | None = None
    status: AdapterStatus
    description: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    required_credentials: list[dict[str, Any]] = Field(default_factory=list)
    operations: list[AdapterOperation] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] | list[Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime
    updated_at: datetime.datetime
