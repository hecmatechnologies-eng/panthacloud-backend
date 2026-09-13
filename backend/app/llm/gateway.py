"""``ModelGateway`` — the single choke point for model access (FR-071, FR-073, FR-074, FR-125).

Every model call goes through here, so allowlisting, context and token caps, timeouts, bounded
retries, the per-organization spend budget, and usage recording cannot be bypassed by a caller. The
gateway owns policy; the provider owns transport.
"""

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderPermanentError,
    ProviderTransientError,
)
from app.llm.pricing import estimate_cost_usd
from app.models.base import utc_now
from app.models.model_usage import ModelUsage

logger = logging.getLogger("fussion.llm.gateway")

# Rough input-token estimate. Exact tokenisation is vendor-specific and unnecessary here: the
# provider rejects an over-long context too, and this exists to fail early and cheaply.
_CHARS_PER_TOKEN = 4


class ModelGatewayError(Exception):
    """Base for gateway policy refusals."""


class ModelNotConfiguredError(ModelGatewayError):
    """No provider is configured. Fail loud; never fabricate an answer (CLAUDE.md §4.10)."""


class ModelNotAllowedError(ModelGatewayError):
    """The requested model is not on the allowlist."""


class ContextTooLargeError(ModelGatewayError):
    """The assembled prompt exceeds the configured input-token cap."""


class ModelCallError(ModelGatewayError):
    """The provider failed after the bounded retries were exhausted."""


class BudgetExceededError(ModelGatewayError):
    """The organization's model spend budget is exhausted or throttled."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Model spend budget exceeded ({reason}).")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class UsageContext:
    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    integration_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None


class ModelGateway:
    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def complete(
        self, db: AsyncSession, request: ModelRequest, context: UsageContext
    ) -> ModelResponse:
        self._check_allowed(request.model)
        self._check_context(request)

        # Project the call's maximum cost so a call that would push the organization over its
        # budget is refused *before* it is made, not discovered after.
        estimated_cost = estimate_cost_usd(
            request.model, _estimate_input_tokens(request), request.max_output_tokens
        )
        throttled_max = await self._check_budget(db, context.organization_id, estimated_cost)
        if throttled_max is not None:
            request = replace(
                request, max_output_tokens=min(request.max_output_tokens, throttled_max)
            )

        started = time.perf_counter()
        response = await self._call_with_retries(request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        await self._record_usage(db, response, context, latency_ms)
        return response

    async def ensure_budget(
        self, db: AsyncSession, organization_id: uuid.UUID, estimated_cost: Decimal = Decimal(0)
    ) -> None:
        """Refuse a call before it is made when the organization is over budget (FR-074).

        The agent adapter calls its provider directly, so the harness checks here before the call
        and records with ``record_external_usage`` after it.
        """
        await self._check_budget(db, organization_id, estimated_cost)

    async def record_external_usage(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int = 0,
        project_id: uuid.UUID | None = None,
        integration_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> None:
        """Record a call made outside ``complete`` — the agent adapter — in the same ledger."""
        db.add(
            ModelUsage(
                organization_id=organization_id,
                project_id=project_id,
                integration_id=integration_id,
                conversation_id=conversation_id,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
                latency_ms=latency_ms,
            )
        )
        await db.flush()

    # --- policy -------------------------------------------------------------------------------

    def _check_allowed(self, model: str) -> None:
        if model not in settings.MODEL_ALLOWED_IDS:
            raise ModelNotAllowedError(f"Model {model!r} is not allowed.")

    def _check_context(self, request: ModelRequest) -> None:
        estimated = sum(_estimate_tokens(m.content) for m in request.messages)
        if estimated > settings.MODEL_MAX_INPUT_TOKENS:
            raise ContextTooLargeError(
                f"Prompt is ~{estimated} tokens, over the {settings.MODEL_MAX_INPUT_TOKENS} cap."
            )

    async def _check_budget(
        self, db: AsyncSession, organization_id: uuid.UUID, estimated_call_cost: Decimal
    ) -> int | None:
        """Return a reduced output-token cap when throttling, or None to proceed unchanged.

        Raises ``BudgetExceededError`` at the suspension threshold. A ``None`` limit is uncapped
        and warns loudly (production refuses it at startup — see ``factory.validate_model_configuration``).
        A non-positive limit is treated as suspended, so a misconfigured budget fails closed.

        The check is not atomic under concurrency: spend is read here and this call's cost is
        written only after it returns, so N in-flight requests can each pass on the same
        pre-call sum and overshoot by up to N × the per-call maximum. The per-organization rate
        limit bounds N; an atomic reservation is a later slice.
        """
        raw_limit = settings.MODEL_DEFAULT_SPEND_LIMIT_USD
        if raw_limit is None:
            logger.warning(
                "MODEL_DEFAULT_SPEND_LIMIT_USD is unset: organization %s is uncapped.",
                organization_id,
            )
            return None
        limit = Decimal(str(raw_limit))
        if limit <= 0:
            raise BudgetExceededError("suspended")

        spend = await self._month_spend(db, organization_id)
        ratio = (spend + estimated_call_cost) / limit
        if ratio >= 1:
            raise BudgetExceededError("suspended")
        if ratio >= Decimal(str(settings.MODEL_BUDGET_THROTTLE_FRACTION)):
            return settings.MODEL_BUDGET_THROTTLED_MAX_OUTPUT_TOKENS
        if ratio >= Decimal(str(settings.MODEL_BUDGET_WARNING_FRACTION)):
            logger.warning(
                "Organization %s is at %.0f%% of its model spend budget.",
                organization_id,
                ratio * 100,
            )
        return None

    async def _month_spend(self, db: AsyncSession, organization_id: uuid.UUID) -> Decimal:
        now = utc_now()
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        stmt = select(func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0)).where(
            ModelUsage.organization_id == organization_id,
            ModelUsage.created_at >= month_start,
        )
        return Decimal(str((await db.execute(stmt)).scalar_one()))

    # --- transport ----------------------------------------------------------------------------

    async def _call_with_retries(self, request: ModelRequest) -> ModelResponse:
        attempts = settings.MODEL_MAX_RETRIES + 1
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(
                    self._provider.complete(request),
                    timeout=settings.MODEL_TIMEOUT_SECONDS,
                )
            except ProviderTransientError as exc:
                if attempt + 1 >= attempts:
                    raise ModelCallError("The model provider is unavailable.") from exc
                await asyncio.sleep(_backoff_seconds(attempt))
            except TimeoutError as exc:
                # A timeout is ambiguous: the provider may have completed and billed. Retrying
                # risks a second charge, so it is terminal. The attempt's cost is not recorded;
                # the budget is a soft cap until a reservation lands.
                raise ModelCallError("The model provider timed out.") from exc
            except ProviderPermanentError as exc:
                # Retrying a rejected request only wastes budget.
                raise ModelCallError("The model provider rejected the request.") from exc
        raise ModelCallError("The model provider is unavailable.")  # pragma: no cover

    async def _record_usage(
        self,
        db: AsyncSession,
        response: ModelResponse,
        context: UsageContext,
        latency_ms: int,
    ) -> None:
        db.add(
            ModelUsage(
                organization_id=context.organization_id,
                project_id=context.project_id,
                integration_id=context.integration_id,
                conversation_id=context.conversation_id,
                provider=response.provider,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                estimated_cost_usd=estimate_cost_usd(
                    response.model, response.usage.input_tokens, response.usage.output_tokens
                ),
                latency_ms=latency_ms,
            )
        )
        await db.flush()


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def _estimate_input_tokens(request: ModelRequest) -> int:
    return sum(_estimate_tokens(message.content) for message in request.messages)


def _backoff_seconds(attempt: int) -> float:
    return min(settings.MODEL_RETRY_BACKOFF_SECONDS * (2**attempt), 8.0)


# --- module-level gateway ---------------------------------------------------------------------
#
# Configured by `lifespan` from settings; tests install a fake explicitly. `None` means no provider
# is configured, which the runtime reports as 503 rather than answering with a fabricated reply.

_gateway: ModelGateway | None = None


def set_model_gateway(gateway: ModelGateway | None) -> None:
    global _gateway
    _gateway = gateway


def get_model_gateway() -> ModelGateway:
    if _gateway is None:
        raise ModelNotConfiguredError("No model provider is configured.")
    return _gateway
