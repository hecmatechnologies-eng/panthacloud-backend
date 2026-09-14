"""Read models for agent-run telemetry and model usage (FR-073, FR-089, FR-090, FR-116).

The control plane exposes what the harness persisted — never re-derives it. ``AgentRun`` carries
the reproducibility record (prompt hash, model + reported version, skill versions, budget) and the
ordered ``AgentToolCall`` log; ``ModelUsage`` carries the cost ledger.
"""

import datetime
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent_run import AgentRunStatus, FailureClass


class AgentToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    outcome: str
    duration_ms: int
    error_message: str | None = None


class AgentRunSummaryRead(BaseModel):
    """List shape: no tool-call log, so listing runs stays one query."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID | None = None
    agent_name: str
    agent_version: str
    status: AgentRunStatus
    current_step: str | None = None
    attempt: int
    model_id: str | None = None
    model_version_reported: str | None = None
    skill_versions: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    tokens_used: int
    cost_usd: Decimal
    failure_class: FailureClass | None = None
    failure_reason: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AgentRunRead(AgentRunSummaryRead):
    """Detail shape: adds the reproducibility hash and the ordered tool-call log."""

    prompt_hash: str | None = None
    tool_calls: list[AgentToolCallRead] = Field(default_factory=list)


class ModelUsageByModel(BaseModel):
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class ModelUsageSummary(BaseModel):
    total_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    by_model: list[ModelUsageByModel] = Field(default_factory=list)


BudgetState = Literal["uncapped", "ok", "warning", "throttled", "suspended"]


class BudgetStatus(BaseModel):
    """Read-only view of the organization's monthly model-spend budget (FR-074).

    The enforcement lives in the model gateway; this reports the same numbers so the Studio can
    show where the tenant stands. ``fraction`` is ``None`` when the budget is uncapped.
    """

    limit_usd: Decimal | None = None
    month_spend_usd: Decimal
    fraction: float | None = None
    state: BudgetState
    warning_fraction: float
    throttle_fraction: float
