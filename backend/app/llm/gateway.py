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
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.base import (
    ModelDelta,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
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


class _TransientExhausted(Exception):
    """A provider failed transiently on every attempt.

    Internal signal, distinct from ``ModelCallError``: it says *this* provider is out, not that the
    request is unservable, which is what licenses trying the next one. It is raised only when
    nothing has reached the caller yet, so replaying the request elsewhere cannot duplicate output.
    """


@dataclass(frozen=True, slots=True)
class UsageContext:
    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    integration_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None


class ModelGateway:
    def __init__(
        self,
        provider: ModelProvider,
        fallback: ModelProvider | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self._provider = provider
        self._fallback = fallback
        self._fallback_model = fallback_model

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

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Stream a completion under the same policy as ``complete``, without holding a session.

        Deliberately takes no ``db``: a stream outlives any sane transaction, and holding one open
        for its lifetime is what leaked the pool in the Studio's own SSE feed (CLAUDE.md §3.6,
        FR-118). The caller therefore owns the two database halves, exactly as the agent adapter
        does — ``ensure_budget`` before the call, ``record_external_usage`` after it. The policy
        that needs no database (allowlist, context cap) is enforced here.

        Retries are bounded to *before the first token*: once a delta has been handed to a caller,
        replaying the stream would duplicate text the visitor has already seen. The same bound is
        what makes a stream failover safe — ``_TransientExhausted`` is raised only while nothing
        has been emitted, so the fallback cannot rewind what the visitor already has.
        """
        self._check_allowed(request.model)
        self._check_context(request)

        chain = self._provider_chain(request)
        last_exc: _TransientExhausted | None = None
        for index, (provider, provider_request) in enumerate(chain):
            try:
                async for event in self._attempt_stream(provider, provider_request):
                    yield event
                return
            except _TransientExhausted as exc:
                last_exc = exc
                if index + 1 < len(chain):
                    logger.warning(
                        "Streaming model provider %s is unavailable; falling back to %s.",
                        provider.name,
                        chain[index + 1][0].name,
                    )
        raise ModelCallError("The model provider is unavailable.") from last_exc

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

    def _provider_chain(
        self, request: ModelRequest
    ) -> list[tuple[ModelProvider, ModelRequest]]:
        """The providers to try, in order, each with the request rewritten for its own vendor.

        The model id is a *logical* name: the caller's chosen model, checked against the allowlist
        once in ``_check_allowed``. A fallback vendor would not recognise it, so the fallback's own
        id replaces it. Without this the fallback would be sent "gemini-2.5-flash" and fail with a
        model-not-found — a failover that cannot succeed at the moment it is needed.
        """
        chain = [(self._provider, request)]
        if self._fallback is not None:
            chain.append(
                (
                    self._fallback,
                    replace(request, model=self._fallback_model or request.model),
                )
            )
        return chain

    async def _call_with_retries(self, request: ModelRequest) -> ModelResponse:
        chain = self._provider_chain(request)
        last_exc: _TransientExhausted | None = None
        for index, (provider, provider_request) in enumerate(chain):
            try:
                return await self._attempt_provider(provider, provider_request)
            except _TransientExhausted as exc:
                last_exc = exc
                if index + 1 < len(chain):
                    logger.warning(
                        "Model provider %s is unavailable; falling back to %s.",
                        provider.name,
                        chain[index + 1][0].name,
                    )
        raise ModelCallError("The model provider is unavailable.") from last_exc

    async def _attempt_provider(
        self, provider: ModelProvider, request: ModelRequest
    ) -> ModelResponse:
        attempts = settings.MODEL_MAX_RETRIES + 1
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(
                    provider.complete(request),
                    timeout=settings.MODEL_TIMEOUT_SECONDS,
                )
            except ProviderTransientError as exc:
                if attempt + 1 >= attempts:
                    raise _TransientExhausted from exc
                await asyncio.sleep(_backoff_seconds(attempt))
            except TimeoutError as exc:
                # A timeout is ambiguous: the provider may have completed and billed. Retrying
                # risks a second charge, so it is terminal. The attempt's cost is not recorded;
                # the budget is a soft cap until a reservation lands.
                raise ModelCallError("The model provider timed out.") from exc
            except ProviderPermanentError as exc:
                # Retrying a rejected request only wastes budget. Deliberately *not* a failover
                # trigger: a request the primary refused is malformed or unauthorised, and the
                # next vendor will refuse it identically — just later, and with the real cause
                # buried. The retry block above is the only place a transient failure can
                # escalate to another provider.
                raise ModelCallError("The model provider rejected the request.") from exc
        raise ModelCallError("The model provider is unavailable.")  # pragma: no cover

    async def _attempt_stream(
        self, provider: ModelProvider, request: ModelRequest
    ) -> AsyncIterator[ModelStreamEvent]:
        attempts = settings.MODEL_MAX_RETRIES + 1
        for attempt in range(attempts):
            emitted = False
            try:
                async for event in _with_idle_timeout(
                    provider.stream(request), settings.MODEL_TIMEOUT_SECONDS
                ):
                    if isinstance(event, ModelDelta):
                        emitted = True
                    yield event
                return
            except ProviderTransientError as exc:
                if emitted:
                    # Replaying on another provider would duplicate text the visitor has already
                    # been shown, so a stream that has started can only fail.
                    raise ModelCallError("The model provider is unavailable.") from exc
                if attempt + 1 >= attempts:
                    raise _TransientExhausted from exc
                await asyncio.sleep(_backoff_seconds(attempt))
            except TimeoutError as exc:
                raise ModelCallError("The model provider timed out.") from exc
            except ProviderPermanentError as exc:
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


async def _with_idle_timeout(
    source: AsyncIterator[ModelStreamEvent], timeout: float
) -> AsyncIterator[ModelStreamEvent]:
    """Re-yield ``source``, failing if no event arrives within ``timeout``.

    A whole-stream deadline would kill a long but healthy answer; what matters is that the provider
    has not gone silent, so the timeout applies between events, not to the total.
    """
    iterator = source.__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return
        yield event


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
