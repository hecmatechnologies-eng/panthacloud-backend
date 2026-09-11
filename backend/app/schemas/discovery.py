import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.discovery import DiscoveryStatus


class Evidence(BaseModel):
    file: str
    reason: str
    line: int | None = None
    symbol: str | None = None


class FrameworkFinding(BaseModel):
    name: str
    version: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class EntrypointFinding(BaseModel):
    path: str
    symbol: str
    framework: str
    type: str
    evidence: list[Evidence] = Field(default_factory=list)


class RouteFinding(BaseModel):
    method: str
    path: str
    handler: str
    framework: str
    source_file: str
    source_line: int | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class ApiContractFinding(BaseModel):
    file: str
    format: str  # "OpenAPI" or "Swagger"
    title: str | None = None
    version: str | None = None
    status: str  # "VALID" or "INVALID"
    servers: list[str] = Field(default_factory=list)
    paths_count: int = 0
    operations_count: int = 0
    routes: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class DependencyFinding(BaseModel):
    name: str
    version_spec: str | None = None
    manifest_file: str
    is_dev: bool = False


class ModuleFinding(BaseModel):
    path: str
    type: str
    language: str
    children_count: int = 0


class ConfigurationFinding(BaseModel):
    file: str
    category: str
    sensitive: bool = False


class DeploymentFinding(BaseModel):
    file: str
    type: str


class DiscoveryResult(BaseModel):
    snapshot_id: uuid.UUID
    commit_sha: str
    repository: dict[str, Any]
    frameworks: list[FrameworkFinding] = Field(default_factory=list)
    entrypoints: list[EntrypointFinding] = Field(default_factory=list)
    routes: list[RouteFinding] = Field(default_factory=list)
    api_contracts: list[ApiContractFinding] = Field(default_factory=list)
    dependencies: list[DependencyFinding] = Field(default_factory=list)
    modules: list[ModuleFinding] = Field(default_factory=list)
    configurations: list[ConfigurationFinding] = Field(default_factory=list)
    deployment: list[DeploymentFinding] = Field(default_factory=list)


class DiscoveryCreate(BaseModel):
    # Optional parameters for discovery configuration
    pass


class DiscoveryRead(BaseModel):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    status: DiscoveryStatus
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)
