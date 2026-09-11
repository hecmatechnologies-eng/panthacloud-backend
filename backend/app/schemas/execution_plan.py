import datetime
import enum
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.execution_plan import ExecutionPlanStatus


class SafetyClassification(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    CONFIGURATION = "CONFIGURATION"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    EXTERNAL_NETWORK = "EXTERNAL_NETWORK"
    CREDENTIAL_REQUIRED = "CREDENTIAL_REQUIRED"


class ExecutionStep(BaseModel):
    id: str = Field(..., description="Deterministic step identifier (e.g. step-1, step-2)")
    order: int = Field(..., description="Deterministic 1-based execution order index")
    adapter_id: uuid.UUID | None = Field(default=None, description="Optional associated IntegrationAdapter ID")
    action: str = Field(..., description="Action name (e.g. validate_configuration_keys, execute_query)")
    description: str = Field(..., description="Detailed description of the planned action")
    safety_classifications: list[SafetyClassification] = Field(default_factory=list, description="Safety tags characterizing this step")
    inputs: list[str] = Field(default_factory=list, description="Declarative input references (variable names only, never values)")
    outputs: list[str] = Field(default_factory=list, description="Declarative output artifacts or state changes produced")
    depends_on: list[str] = Field(default_factory=list, description="List of preceding step IDs this step depends upon")
    requires_approval: bool = Field(default=False, description="Whether human approval is strictly required before future execution")
    status: str = Field(default="BLOCKED", description="Current execution readiness status (READY, BLOCKED, REVIEW_REQUIRED)")
    blocked_reason: str | None = Field(default=None, description="Explanation why external execution is blocked in Phase 08")
    evidence: dict[str, Any] | list[Any] = Field(default_factory=dict, description="Evidence references linking to source facts")


class ExecutionPlanCreate(BaseModel):
    integration_plan_id: uuid.UUID | None = Field(default=None, description="Optional explicit integration plan ID to generate execution plan from")


class ExecutionPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    snapshot_id: uuid.UUID
    integration_plan_id: uuid.UUID
    status: ExecutionPlanStatus
    steps: list[ExecutionStep] = Field(default_factory=list)
    required_credentials: list[dict[str, Any]] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] | list[Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime
    updated_at: datetime.datetime
