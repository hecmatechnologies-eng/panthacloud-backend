import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.contract import ContractSource, ContractStatus


class AuthenticationScheme(BaseModel):
    name: str
    type: str
    scheme: str | None = None
    bearer_format: str | None = None
    in_location: str | None = Field(default=None, alias="in")
    description: str | None = None
    flows: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True)


class ReconciliationFinding(BaseModel):
    path: str
    method: str
    category: str  # "MATCHED", "DOCUMENTED_ONLY", "IMPLEMENTED_ONLY", "CONFLICT"
    details: str | None = None
    contract_operation_id: str | None = None
    source_file: str | None = None
    source_line: int | None = None


class ContractReconciliation(BaseModel):
    matched_count: int = 0
    documented_only_count: int = 0
    implemented_only_count: int = 0
    conflict_count: int = 0
    findings: list[ReconciliationFinding] = Field(default_factory=list)


class ApiOperationRead(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    method: str
    path: str
    operation_id: str | None = None
    summary: str | None = None
    description: str | None = None
    source: ContractSource
    source_file: str | None = None
    source_line: int | None = None
    authentication_required: bool = False
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ApiContractRead(BaseModel):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    discovery_run_id: uuid.UUID
    status: ContractStatus
    title: str
    version: str
    format: str
    servers: list[dict[str, Any]] = Field(default_factory=list)
    authentication: list[dict[str, Any]] = Field(default_factory=list)
    schemas: dict[str, Any] = Field(default_factory=dict)
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    operations: list[ApiOperationRead] = Field(default_factory=list)
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ContractCreate(BaseModel):
    discovery_run_id: uuid.UUID | None = None
