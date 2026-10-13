"""Provider failover — the gateway's behaviour when the primary quota is gone (FR-072).

The claim under test is narrow and worth stating, because the obvious test would pass without
proving anything: *when the primary fails transiently on every attempt, the request is served by
the fallback instead of raising.*

These tests assert the four things that make that true, each of which can hold while the gateway
still fails in production:

1. the fallback is actually reached, rather than the error propagating;
2. the request sent to the fallback names the *fallback's* model, not the caller's — a failover
   that forwards "gemini-2.5-flash" to OpenRouter fails with model-not-found, which is precisely
   the moment the failover was needed;
3. a permanent rejection does **not** fail over, so a malformed request is still reported as
   malformed instead of as an outage one vendor later;
4. a stream that has already emitted text never fails over, because replaying it would duplicate
   what the visitor has been shown.

No network and no paid API: both providers are fakes.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.base import (
    ModelDelta,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ProviderPermanentError,
    ProviderTransientError,
)
from app.llm.factory import validate_model_configuration
from app.llm.gateway import ModelCallError, ModelGateway, UsageContext
from app.llm.providers.fake import FakeModelProvider
from app.models.model_usage import ModelUsage

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "openrouter/free"


@pytest.fixture(autouse=True)
def _allow_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """State this module's model, rather than inheriting the deployment's allowlist."""
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [PRIMARY_MODEL])


def _request() -> ModelRequest:
    return ModelRequest(
        model=PRIMARY_MODEL,
        messages=[ModelMessage(role="user", content="hello")],
        max_output_tokens=128,
    )


def _gateway(primary: FakeModelProvider, fallback: FakeModelProvider | None) -> ModelGateway:
    return ModelGateway(
        primary,
        fallback=fallback,
        fallback_model=FALLBACK_MODEL if fallback is not None else None,
    )


def _degraded_primary() -> FakeModelProvider:
    """A primary that is out of quota: 429 on every attempt, for the whole retry budget."""
    return FakeModelProvider(error=ProviderTransientError("quota exhausted"))


class _DiesMidStream:
    """Emits text, then fails — the case a plain ``FakeModelProvider`` cannot express.

    Its ``error`` fires before any delta, so it can only ever test failover-before-emission. This
    fake exists for the opposite guarantee: a stream that has *started* must not be replayed.
    """

    name = "partial"

    def __init__(self, before: str = "half an answer") -> None:
        self.before = before
        self.calls: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover
        raise ProviderTransientError("not used by these tests")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.calls.append(request)
        yield ModelDelta(text=self.before)
        raise ProviderTransientError("died mid-stream")


# --- complete ---------------------------------------------------------------------------------


async def test_transient_primary_is_served_by_the_fallback(db_session: AsyncSession):
    fallback = FakeModelProvider(reply="answered by the fallback")
    fallback.name = "fallback-provider"
    gateway = _gateway(_degraded_primary(), fallback)

    response = await gateway.complete(
        db_session, _request(), UsageContext(organization_id=uuid.uuid4())
    )

    assert response.text == "answered by the fallback"
    assert fallback.calls, "the fallback was never reached"


async def test_fallback_request_names_the_fallback_model(db_session: AsyncSession):
    fallback = FakeModelProvider()
    gateway = _gateway(_degraded_primary(), fallback)

    await gateway.complete(db_session, _request(), UsageContext(organization_id=uuid.uuid4()))

    assert [c.model for c in fallback.calls] == [FALLBACK_MODEL]
    # The primary keeps seeing the caller's own model, on every retry. The assertion is about the
    # model id rather than the call count: the primary is retried to its full budget first, so
    # how many times it was asked is a separate concern (asserted in test_both_providers_down).
    assert {c.model for c in gateway._provider.calls} == {PRIMARY_MODEL}


async def test_permanent_primary_error_does_not_fail_over(db_session: AsyncSession):
    """A rejected request is malformed or unauthorised; the next vendor refuses it identically."""
    fallback = FakeModelProvider(reply="should never be returned")
    gateway = _gateway(FakeModelProvider(error=ProviderPermanentError("400 bad request")), fallback)

    with pytest.raises(ModelCallError):
        await gateway.complete(db_session, _request(), UsageContext(organization_id=uuid.uuid4()))

    assert not fallback.calls, "a permanent error must not be replayed on another provider"


async def test_healthy_primary_never_touches_the_fallback(db_session: AsyncSession):
    fallback = FakeModelProvider()
    gateway = _gateway(FakeModelProvider(reply="primary answer"), fallback)

    response = await gateway.complete(
        db_session, _request(), UsageContext(organization_id=uuid.uuid4())
    )

    assert response.text == "primary answer"
    assert not fallback.calls


async def test_no_fallback_configured_still_raises(db_session: AsyncSession):
    """Unconfigured failover must behave exactly as before: the error propagates."""
    gateway = _gateway(_degraded_primary(), None)

    with pytest.raises(ModelCallError):
        await gateway.complete(db_session, _request(), UsageContext(organization_id=uuid.uuid4()))


async def test_both_providers_down_raises(db_session: AsyncSession):
    """Each provider gets the full retry budget; only then does the call fail."""
    primary = _degraded_primary()
    fallback = FakeModelProvider(error=ProviderTransientError("also down"))
    gateway = _gateway(primary, fallback)

    with pytest.raises(ModelCallError):
        await gateway.complete(db_session, _request(), UsageContext(organization_id=uuid.uuid4()))

    assert len(primary.calls) == settings.MODEL_MAX_RETRIES + 1
    assert len(fallback.calls) == settings.MODEL_MAX_RETRIES + 1


async def test_ledger_records_the_provider_that_actually_answered(db_session: AsyncSession):
    """A failover must be visible in usage, or "which model answered this" becomes unknowable."""
    fallback = FakeModelProvider(reply="fallback answer")
    fallback.name = "fallback-provider"
    gateway = _gateway(_degraded_primary(), fallback)

    await gateway.complete(
        db_session, _request(), UsageContext(organization_id=uuid.uuid4())
    )

    rows = list((await db_session.execute(select(ModelUsage))).scalars())
    assert len(rows) == 1
    assert rows[0].provider == "fallback-provider"
    assert rows[0].model == FALLBACK_MODEL


# --- stream -----------------------------------------------------------------------------------


async def _collect(iterator) -> list[ModelStreamEvent]:
    return [event async for event in iterator]


async def test_stream_fails_over_when_nothing_has_been_emitted():
    fallback = FakeModelProvider(reply="fallback")
    gateway = _gateway(_degraded_primary(), fallback)

    events = await _collect(gateway.stream(_request()))

    text = "".join(e.text for e in events if isinstance(e, ModelDelta))
    assert text == "fallback"
    assert [c.model for c in fallback.calls] == [FALLBACK_MODEL]


async def test_stream_does_not_fail_over_after_emitting_a_delta():
    """Replaying would hand the visitor the text twice, so a started stream can only fail."""
    fallback = FakeModelProvider(reply="should never be returned")
    gateway = ModelGateway(
        _DiesMidStream(), fallback=fallback, fallback_model=FALLBACK_MODEL
    )

    with pytest.raises(ModelCallError):
        await _collect(gateway.stream(_request()))

    assert not fallback.calls, "a stream that already emitted text must not be replayed"


# --- configuration ----------------------------------------------------------------------------


def _declare(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    monkeypatch.setattr(settings, "MODEL_ID", PRIMARY_MODEL)
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [PRIMARY_MODEL])
    monkeypatch.setattr(settings, "MODEL_FALLBACK_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "MODEL_FALLBACK_API_KEY", "sk-or-test")
    monkeypatch.setattr(settings, "MODEL_FALLBACK_ID", FALLBACK_MODEL)
    monkeypatch.setattr(settings, "MODEL_FALLBACK_ALLOWED_IDS", [FALLBACK_MODEL])
    for name, value in overrides.items():
        monkeypatch.setattr(settings, name, value)


def test_validation_rejects_a_fallback_model_outside_its_allowlist(monkeypatch):
    _declare(monkeypatch, MODEL_FALLBACK_ID="some/unvetted-model")

    with pytest.raises(RuntimeError, match="MODEL_FALLBACK_ID"):
        validate_model_configuration()


def test_validation_accepts_an_allowlisted_fallback(monkeypatch):
    _declare(monkeypatch)
    validate_model_configuration()  # must not raise


def test_failover_off_is_not_subject_to_the_fallback_allowlist(monkeypatch):
    """No key means no failover, so an unconfigured deployment cannot fail validation."""
    _declare(monkeypatch, MODEL_FALLBACK_API_KEY=None, MODEL_FALLBACK_ID="some/unvetted-model")

    validate_model_configuration()  # must not raise