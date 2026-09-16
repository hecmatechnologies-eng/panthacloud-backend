"""The tool gateway — the single choke point for tool execution (FR-065, FR-066, FR-069).

Every tool invocation passes through here: authorization happens outside the model, execution
happens once, and the call is recorded. Read tools are auto-authorized for an agent holding the
required capability; write tools additionally require an approved plan. Sensitive argument values
are redacted before they reach the run record.
"""

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.harness.context import ExecutionContext
from app.models.agent_run import AgentRun, AgentToolCall
from app.tools.base import Tool, ToolError, ToolKind, ToolResult
from app.tools.registry import ToolNotFoundError, ToolRegistry

logger = logging.getLogger("fussion.tools.gateway")

# A key is sensitive if any of its word-tokens is in this set. Token matching (rather than a
# substring test) keeps `path` and `keyword` safe while catching `api_key`, `githubToken`,
# `X-Api-Key` and `session_id`. Over-redaction is the safe direction (FR-069).
_SENSITIVE_TOKENS = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "key",
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "cookie",
        "session",
        "signature",
        "pat",
        "credential",
        "credentials",
    }
)
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+|(?<=[a-z0-9])(?=[A-Z])")
_REDACTED = "[REDACTED]"


@dataclass(frozen=True, slots=True)
class ApprovedPlan:
    """Proof that a human approved the plan a write tool acts on (FR-066)."""

    plan_id: str
    approved_by: uuid.UUID


class ToolGateway:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        # pydantic-ai runs the model's tool calls concurrently (its ToolManager default is
        # 'parallel'), and every call appends to the run's tool-call log on the one AsyncSession.
        # An AsyncSession is not safe for concurrent use: two interleaved flushes put the session
        # in a pending-rollback state and the run died with "the connection is closed". This lock
        # serializes the log write only — tool execution itself stays parallel.
        self._record_lock = asyncio.Lock()

    async def execute(
        self,
        db: AsyncSession,
        run: AgentRun,
        context: ExecutionContext,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        approved_plan: ApprovedPlan | None = None,
    ) -> ToolResult:
        arguments = arguments or {}
        _assert_run_belongs_to_context(run, context)

        try:
            tool = self._registry.get(tool_name)
        except ToolNotFoundError as exc:
            # An unknown tool is a model mistake to recover from, not a policy denial.
            return await self._record(db, run, tool_name, arguments, "unknown", str(exc))

        denial = self._denial_reason(context, tool, approved_plan)
        if denial is not None:
            return await self._record(db, run, tool_name, arguments, "denied", denial, denied=True)

        try:
            validated = tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            return await self._record(
                db, run, tool_name, arguments, "error", _validation_message(tool, exc)
            )

        started = time.perf_counter()
        try:
            result = await tool.execute(context, validated)
        except ToolError as exc:
            result = ToolResult(error=str(exc))
        except Exception:
            logger.exception("Tool %r raised an unexpected exception.", tool_name)
            result = ToolResult(error="The tool failed unexpectedly.")
        duration_ms = int((time.perf_counter() - started) * 1000)

        await self._record_call(
            db,
            run,
            tool_name=tool_name,
            arguments=arguments,
            outcome="error" if result.is_error else "ok",
            duration_ms=duration_ms,
            error_message=result.error,
        )
        return result

    def _denial_reason(
        self, context: ExecutionContext, tool: Tool, approved_plan: ApprovedPlan | None
    ) -> str | None:
        if not context.has_capability(tool.required_capability):
            return (
                f"Not permitted: this agent lacks the {tool.required_capability!r} capability."
            )
        if tool.kind is ToolKind.WRITE and approved_plan is None:
            return "Not permitted: a write tool requires an approved plan."
        return None

    async def _record(
        self,
        db: AsyncSession,
        run: AgentRun,
        tool_name: str,
        arguments: dict[str, Any],
        outcome: str,
        message: str,
        *,
        denied: bool = False,
    ) -> ToolResult:
        await self._record_call(
            db,
            run,
            tool_name=tool_name,
            arguments=arguments,
            outcome=outcome,
            duration_ms=0,
            error_message=message,
        )
        return ToolResult(error=message, denied=denied)

    async def _record_call(
        self,
        db: AsyncSession,
        run: AgentRun,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        outcome: str,
        duration_ms: int,
        error_message: str | None = None,
    ) -> AgentToolCall:
        """Append to the run's tool-call log under the gateway's write lock (see ``__init__``)."""
        async with self._record_lock:
            return await record_tool_call(
                db,
                run,
                tool_name=tool_name,
                arguments=arguments,
                outcome=outcome,
                duration_ms=duration_ms,
                error_message=error_message,
            )


async def record_tool_call(
    db: AsyncSession,
    run: AgentRun,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    outcome: str,
    duration_ms: int,
    error_message: str | None = None,
) -> AgentToolCall:
    """Append one ordered entry to the run's tool-call log (FR-069, FR-090).

    Redaction happens here, not at the call site, so no caller can persist a secret by forgetting
    to wrap its arguments.
    """
    call = AgentToolCall(
        agent_run_id=run.id,
        sequence=await _next_sequence(db, run.id),
        tool_name=tool_name,
        arguments=redact_arguments(arguments),
        outcome=outcome,
        duration_ms=duration_ms,
        error_message=error_message,
    )
    db.add(call)
    await db.flush()
    return call


async def _next_sequence(db: AsyncSession, agent_run_id: uuid.UUID) -> int:
    stmt = select(func.max(AgentToolCall.sequence)).where(
        AgentToolCall.agent_run_id == agent_run_id
    )
    current = (await db.execute(stmt)).scalar_one_or_none()
    return (current or 0) + 1


def _assert_run_belongs_to_context(run: AgentRun, context: ExecutionContext) -> None:
    """A tool call must be authorized and recorded against the same tenant."""
    if run.organization_id != context.organization_id or run.project_id != context.project_id:
        raise ValueError("AgentRun does not belong to the ExecutionContext's tenant.")
    if context.agent_run_id is not None and context.agent_run_id != run.id:
        raise ValueError("ExecutionContext is bound to a different AgentRun.")


def _validation_message(tool: Tool, exc: ValidationError) -> str:
    """A concise, model-readable reason; never echoes the submitted values (they may be secrets)."""
    problems = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "arguments"
        problems.append(f"{location}: {error['msg']}")
    return f"Invalid arguments for {tool.name!r}: " + "; ".join(problems)


def _is_sensitive_key(key: str) -> bool:
    tokens = {token.lower() for token in _TOKEN_SPLIT.split(key) if token}
    return bool(tokens & _SENSITIVE_TOKENS)


def redact_arguments(value: Any, key: str | None = None) -> Any:
    """Recursively replace values whose key looks sensitive (FR-069)."""
    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {k: redact_arguments(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_arguments(item) for item in value]
    return value
