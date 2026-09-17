"""Step B · B5 — ModelGateway policy (FR-071, FR-073, FR-074).

Unit tests against the gateway with fake providers: allowlist, context cap, budget warning /
throttle / suspension, bounded retries, and usage recording. No network, no paid API.
"""

import asyncio
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_session_factory
from app.llm.base import (
    ModelDelta,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ProviderPermanentError,
    ProviderTransientError,
    StreamDone,
    Usage,
)
from app.llm.factory import validate_model_configuration
from app.llm.gateway import (
    BudgetExceededError,
    ContextTooLargeError,
    ModelCallError,
    ModelGateway,
    ModelNotAllowedError,
    ModelNotConfiguredError,
    UsageContext,
    get_model_gateway,
    set_model_gateway,
)
from app.llm.pricing import estimate_cost_usd
from app.llm.providers.fake import FakeModelProvider
from app.models.model_usage import ModelUsage

MODEL = "gemini-2.5-flash"


@pytest.fixture(autouse=True)
def _allow_the_test_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Declare this module's model allowed, rather than inheriting the deployment's allowlist.

    The gateway refuses any model not on `settings.MODEL_ALLOWED_IDS`. Reading that from `.env` made
    the suite's outcome depend on local configuration — and no single value satisfies both this
    module (which pins a fixed model id) and the public-chat tests (which use the deployment's
    `MODEL_ID`). Each module now states what it needs.
    """
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [MODEL])


def _request(text: str = "hello", max_output_tokens: int = 128) -> ModelRequest:
    return ModelRequest(
        model=MODEL,
        messages=[ModelMessage(role="user", content=text)],
        max_output_tokens=max_output_tokens,
    )


async def _seed_spend(organization_id: uuid.UUID, amount: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            ModelUsage(
                organization_id=organization_id,
                provider="seed",
                model=MODEL,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=Decimal(amount),
                latency_ms=0,
            )
        )
        await db.commit()


class _TransientThenSuccess:
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            raise ProviderTransientError("boom")
        return ModelResponse(text="ok", model=request.model, provider=self.name, usage=Usage(1, 1))


class _AlwaysTransient:
    name = "transient"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        raise ProviderTransientError("boom")


class _AlwaysPermanent:
    name = "permanent"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        raise ProviderPermanentError("rejected")


class _AlwaysTimeout:
    name = "timeout"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        raise TimeoutError("slow")


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_RETRY_BACKOFF_SECONDS", 0.0)


# ============================================================
# Allowlist & context cap
# ============================================================


@pytest.mark.asyncio
async def test_allowed_model_records_usage() -> None:
    provider = FakeModelProvider(reply="hi", usage=Usage(1000, 500))
    gateway = ModelGateway(provider)
    org = uuid.uuid4()

    session_factory = get_session_factory()
    async with session_factory() as db:
        response = await gateway.complete(db, _request(), UsageContext(organization_id=org))
        await db.commit()

    assert response.text == "hi"
    async with session_factory() as db:
        row = (await db.execute(select(ModelUsage))).scalar_one()
    assert row.organization_id == org
    assert (row.input_tokens, row.output_tokens) == (1000, 500)
    assert abs(row.estimated_cost_usd - estimate_cost_usd(MODEL, 1000, 500)) < Decimal("0.000001")


@pytest.mark.asyncio
async def test_disallowed_model_is_refused() -> None:
    gateway = ModelGateway(FakeModelProvider())
    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ModelNotAllowedError):
            await gateway.complete(
                db,
                ModelRequest(
                    model="not-allowed",
                    messages=[ModelMessage(role="user", content="hi")],
                    max_output_tokens=10,
                ),
                UsageContext(organization_id=uuid.uuid4()),
            )


@pytest.mark.asyncio
async def test_context_cap_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_MAX_INPUT_TOKENS", 5)
    gateway = ModelGateway(FakeModelProvider())
    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ContextTooLargeError):
            await gateway.complete(
                db,
                _request(text="x" * 1000),
                UsageContext(organization_id=uuid.uuid4()),
            )


# ============================================================
# Budget (FR-074)
# ============================================================


@pytest.mark.asyncio
async def test_budget_suspends_at_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", 0.5)
    org = uuid.uuid4()
    await _seed_spend(org, "1.0")
    gateway = ModelGateway(FakeModelProvider())

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(BudgetExceededError) as excinfo:
            await gateway.complete(db, _request(), UsageContext(organization_id=org))
    assert excinfo.value.reason == "suspended"


@pytest.mark.asyncio
async def test_budget_throttles_output_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", 1.0)
    monkeypatch.setattr(settings, "MODEL_BUDGET_THROTTLED_MAX_OUTPUT_TOKENS", 256)
    org = uuid.uuid4()
    await _seed_spend(org, "0.96")  # 96% — in the throttle band
    provider = FakeModelProvider()
    gateway = ModelGateway(provider)

    session_factory = get_session_factory()
    async with session_factory() as db:
        await gateway.complete(
            db, _request(max_output_tokens=4096), UsageContext(organization_id=org)
        )
    assert provider.calls[0].max_output_tokens == 256


@pytest.mark.asyncio
async def test_budget_warning_allows_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", 1.0)
    org = uuid.uuid4()
    await _seed_spend(org, "0.85")  # 85% — warning band, not a refusal
    provider = FakeModelProvider()
    gateway = ModelGateway(provider)

    session_factory = get_session_factory()
    async with session_factory() as db:
        await gateway.complete(db, _request(), UsageContext(organization_id=org))
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_budget_suspends_when_projected_cost_would_exceed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Spend is below the limit, but the projected cost of this call is not: it must be refused
    # before it is made, not after.
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", 0.001)
    org = uuid.uuid4()
    await _seed_spend(org, "0.0005")
    gateway = ModelGateway(FakeModelProvider())

    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(BudgetExceededError):
            await gateway.complete(
                db, _request(max_output_tokens=1024), UsageContext(organization_id=org)
            )


# ============================================================
# Retries
# ============================================================


@pytest.mark.asyncio
async def test_transient_error_is_retried_then_succeeds() -> None:
    provider = _TransientThenSuccess()
    gateway = ModelGateway(provider)
    session_factory = get_session_factory()
    async with session_factory() as db:
        response = await gateway.complete(db, _request(), UsageContext(organization_id=uuid.uuid4()))
    assert response.text == "ok"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_permanent_error_is_not_retried() -> None:
    provider = _AlwaysPermanent()
    gateway = ModelGateway(provider)
    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ModelCallError):
            await gateway.complete(db, _request(), UsageContext(organization_id=uuid.uuid4()))
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_retries_are_bounded() -> None:
    provider = _AlwaysTransient()
    gateway = ModelGateway(provider)
    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ModelCallError):
            await gateway.complete(db, _request(), UsageContext(organization_id=uuid.uuid4()))
    assert provider.calls == settings.MODEL_MAX_RETRIES + 1


@pytest.mark.asyncio
async def test_timeout_is_not_retried() -> None:
    # A timeout may have completed and billed provider-side; retrying could double-charge.
    provider = _AlwaysTimeout()
    gateway = ModelGateway(provider)
    session_factory = get_session_factory()
    async with session_factory() as db:
        with pytest.raises(ModelCallError):
            await gateway.complete(db, _request(), UsageContext(organization_id=uuid.uuid4()))
    assert provider.calls == 1


# ============================================================
# Configuration & pricing
# ============================================================


@pytest.mark.asyncio
async def test_unconfigured_gateway_fails_loud() -> None:
    set_model_gateway(None)
    with pytest.raises(ModelNotConfiguredError):
        get_model_gateway()


def test_estimate_cost() -> None:
    assert estimate_cost_usd(MODEL, 1_000_000, 0) == Decimal("0.30")
    assert estimate_cost_usd(MODEL, 0, 1_000_000) == Decimal("2.50")
    assert estimate_cost_usd("unknown-model", 1_000_000, 1_000_000) == Decimal(0)


def test_validate_rejects_model_id_not_in_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_ID", "not-allowed")
    with pytest.raises(RuntimeError):
        validate_model_configuration()


def test_validate_rejects_uncapped_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "MODEL_DEFAULT_SPEND_LIMIT_USD", None)
    with pytest.raises(RuntimeError):
        validate_model_configuration()


# ============================================================
# Streaming (B7)
# ============================================================


class _ScriptedProvider:
    """A provider whose stream fails a set number of times, optionally after a first delta."""

    name = "fake"

    def __init__(self, *, failures: int = 0, emit_before_failure: bool = False) -> None:
        self._failures = failures
        self._emit_before_failure = emit_before_failure
        self.attempts = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover
        raise AssertionError("complete() is not used by these tests")

    async def stream(self, request: ModelRequest):
        self.attempts += 1
        if self.attempts <= self._failures:
            if self._emit_before_failure:
                yield ModelDelta(text="partial ")
            raise ProviderTransientError("transient")
        yield ModelDelta(text="ok")
        yield StreamDone(text="ok", model=request.model, provider=self.name, usage=Usage(2, 3))


class _StallingProvider:
    name = "fake"

    async def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover
        raise AssertionError("complete() is not used by these tests")

    async def stream(self, request: ModelRequest):
        await asyncio.sleep(5)
        yield StreamDone(text="late", model=request.model, provider=self.name, usage=Usage(0, 0))


@pytest.mark.asyncio
async def test_stream_yields_deltas_then_the_done_event() -> None:
    provider = FakeModelProvider(reply="one two three")
    events = [event async for event in ModelGateway(provider).stream(_request())]

    assert [e.text for e in events if isinstance(e, ModelDelta)] == ["one", " two", " three"]
    done = events[-1]
    assert isinstance(done, StreamDone)
    # The terminal event carries the whole text, so a caller never accumulates deltas itself.
    assert done.text == "one two three"
    assert done.usage == Usage(input_tokens=10, output_tokens=5)


@pytest.mark.asyncio
async def test_stream_refuses_a_model_not_on_the_allowlist() -> None:
    request = replace(_request(), model="not-allowed")
    with pytest.raises(ModelNotAllowedError):
        [event async for event in ModelGateway(FakeModelProvider()).stream(request)]


@pytest.mark.asyncio
async def test_stream_refuses_an_over_long_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_MAX_INPUT_TOKENS", 5)
    with pytest.raises(ContextTooLargeError):
        [event async for event in ModelGateway(FakeModelProvider()).stream(_request("x" * 400))]


@pytest.mark.asyncio
async def test_stream_retries_a_transient_failure_before_the_first_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MODEL_RETRY_BACKOFF_SECONDS", 0.0)
    provider = _ScriptedProvider(failures=1)

    events = [event async for event in ModelGateway(provider).stream(_request())]

    assert provider.attempts == 2
    assert [e.text for e in events if isinstance(e, ModelDelta)] == ["ok"]


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_the_first_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replaying a half-delivered answer would duplicate text the visitor has already seen."""
    monkeypatch.setattr(settings, "MODEL_RETRY_BACKOFF_SECONDS", 0.0)
    provider = _ScriptedProvider(failures=1, emit_before_failure=True)

    with pytest.raises(ModelCallError):
        [event async for event in ModelGateway(provider).stream(_request())]

    assert provider.attempts == 1


@pytest.mark.asyncio
async def test_stream_fails_on_a_silent_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MODEL_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(ModelCallError):
        [event async for event in ModelGateway(_StallingProvider()).stream(_request())]


@pytest.mark.asyncio
async def test_stream_leaves_the_ledger_to_the_caller() -> None:
    """The gateway holds no session during a stream (FR-118), so it cannot record usage itself."""
    [event async for event in ModelGateway(FakeModelProvider()).stream(_request())]

    session_factory = get_session_factory()
    async with session_factory() as db:
        assert (await db.execute(select(ModelUsage))).scalars().all() == []
