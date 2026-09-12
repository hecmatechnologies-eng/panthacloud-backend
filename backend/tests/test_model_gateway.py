"""Step B · B5 — ModelGateway policy (FR-071, FR-073, FR-074).

Unit tests against the gateway with fake providers: allowlist, context cap, budget warning /
throttle / suspension, bounded retries, and usage recording. No network, no paid API.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_session_factory
from app.llm.base import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ProviderPermanentError,
    ProviderTransientError,
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
