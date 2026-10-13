"""The OpenAI-compatible adapter, which had no tests at all (FR-072).

Two reasons this file exists. The first is that a module with no tests is where behaviour quietly
breaks: `_map_error` decides whether the gateway retries, fails over, or gives up, and every one of
those paths is driven by a single `isinstance` check.

The second is the empty-completion rule, which is easy to get backwards in both directions. An
empty answer from a *router* — a model id that picks a different underlying model per request — is
a property of the model it happened to land on, so the retry is expected to select another and
succeed. An empty answer from a *fixed* model is a prompt or content problem that will recur
exactly, so it must stay terminal: retrying it wastes the whole retry budget to arrive at the same
non-answer, and worse, it hands the caller an "unavailable" error instead of telling them the
request had no answer.

The client is injected, so none of this needs a network or a key.
"""

import uuid

import pytest

from app.core.config import settings
from app.llm.base import (
    ModelDelta,
    ModelMessage,
    ModelRequest,
    ProviderPermanentError,
    ProviderTransientError,
    StreamDone,
)
from app.llm.factory import build_model_gateway
from app.llm.gateway import ModelGateway, UsageContext
from app.llm.providers.openai_compatible import OpenAICompatibleProvider

ROUTER_ID = "openrouter/free"
FIXED_ID = "some/model"


class _Message:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = _Message(content)
        self.delta = _Message(content)


class _Completion:
    def __init__(self, content: str | None, model: str = "some/model") -> None:
        self.model = model
        self.choices = [_Choice(content)] if content is not None else [_Choice(None)]
        self.usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 3})()


class _Chunk:
    def __init__(self, content: str | None, model: str = "some/model") -> None:
        self.model = model
        self.choices = [_Choice(content)] if content is not None else []
        self.usage = None


class _AsyncChunks:
    """An async iterable of chunks.

    The adapter does ``async for chunk in stream`` over what the client returns, so a plain list
    raises TypeError — which is itself worth having had to discover here rather than in production.
    """

    def __init__(self, chunks: list) -> None:
        self._chunks = list(chunks)

    def __aiter__(self):
        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


class _StubCompletions:
    """Returns each queued response in turn, recording every call."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs) -> object:
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        return _AsyncChunks(response) if isinstance(response, list) else response


class _StubClient:
    def __init__(self, responses: list) -> None:
        self.completions = _StubCompletions(responses)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _provider(responses: list, *, retry_on_empty: bool) -> OpenAICompatibleProvider:
    client = _StubClient(responses)
    provider = OpenAICompatibleProvider(
        "key", "https://example.invalid/v1", name="stub", retry_on_empty=retry_on_empty,
        client=client,
    )
    return provider


def _request(model: str = FIXED_ID) -> ModelRequest:
    return ModelRequest(
        model=model,
        messages=[ModelMessage(role="user", content="hi")],
        max_output_tokens=64,
    )


# --- empty completions -----------------------------------------------------------------------


async def test_fixed_model_empty_completion_is_permanent():
    """Retrying would repeat the identical non-answer and mislabel it as an outage."""
    provider = _provider([_Completion("")], retry_on_empty=False)

    with pytest.raises(ProviderPermanentError):
        await provider.complete(_request())


async def test_router_empty_completion_is_transient():
    """The retry lands on a different model, so this is worth retrying."""
    provider = _provider([_Completion("")], retry_on_empty=True)

    with pytest.raises(ProviderTransientError):
        await provider.complete(_request())


async def test_router_retries_until_a_model_answers(db_session, monkeypatch):
    """The point of the rule, end to end: two empty picks, then an answer.

    The retry is the *gateway's* job, not the adapter's — the adapter only classifies the failure.
    So this drives a real ``ModelGateway`` over the real adapter, which is the only way the claim
    "an empty router response is retried rather than fatal" can be true or false.
    """
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [ROUTER_ID])
    monkeypatch.setattr(settings, "MODEL_RETRY_BACKOFF_SECONDS", 0.0)
    client = _StubClient([_Completion(""), _Completion(""), _Completion("pong")])
    provider = OpenAICompatibleProvider(
        "key", "https://example.invalid/v1", name="stub", retry_on_empty=True, client=client
    )

    response = await ModelGateway(provider).complete(
        db_session, _request(ROUTER_ID), UsageContext(organization_id=uuid.uuid4())
    )

    assert response.text == "pong"
    assert len(client.completions.calls) == 3


async def test_no_choices_at_all_is_also_empty():
    """A body with no choices is as empty as one whose content is blank."""
    provider = _provider([_Completion(None)], retry_on_empty=True)

    with pytest.raises(ProviderTransientError):
        await provider.complete(_request(ROUTER_ID))


# --- request shaping --------------------------------------------------------------------------


async def test_request_carries_the_model_and_budget():
    provider = _provider([_Completion("ok")], retry_on_empty=False)

    await provider.complete(_request(FIXED_ID))

    sent = provider._client.completions.calls[0]
    assert sent["model"] == FIXED_ID
    assert sent["max_tokens"] == 64
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    # Absent temperature must stay absent: sending null makes some vendors reject the request.
    assert "temperature" not in sent


async def test_usage_and_provider_are_reported_from_the_response():
    provider = _provider([_Completion("ok", model="vendor/real-model")], retry_on_empty=False)

    response = await provider.complete(_request())

    assert response.provider == "stub"
    assert response.model == "vendor/real-model"
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 3


# --- streaming --------------------------------------------------------------------------------


async def _collect(provider: OpenAICompatibleProvider):
    return [event async for event in provider.stream(_request(ROUTER_ID))]


def _stream_of(*contents: str) -> list:
    return [_Chunk(content) if content else _Chunk(None) for content in contents]


async def test_stream_yields_deltas_then_done():
    provider = _provider([_stream_of("hel", "lo")], retry_on_empty=False)

    events = await _collect(provider)

    assert [e.text for e in events if isinstance(e, ModelDelta)] == ["hel", "lo"]
    assert isinstance(events[-1], StreamDone)
    assert events[-1].text == "hello"


async def test_router_empty_stream_is_retryable_rather_than_silently_empty():
    """A stream that emits nothing must not become a blank message in the visitor's chat."""
    provider = _provider([_stream_of()], retry_on_empty=True)

    with pytest.raises(ProviderTransientError):
        await _collect(provider)


async def test_fixed_model_empty_stream_is_unchanged():
    """Preserved behaviour: a fixed model's empty stream is a real empty answer."""
    provider = _provider([_stream_of()], retry_on_empty=False)

    events = await _collect(provider)

    assert len(events) == 1
    assert isinstance(events[0], StreamDone)
    assert events[0].text == ""


async def test_stream_requests_usage_so_the_ledger_can_be_filled():
    """Usage is only sent by OpenAI-shaped APIs when asked, and the ledger needs it."""
    provider = _provider([_stream_of("hi")], retry_on_empty=False)

    await _collect(provider)

    assert provider._client.completions.calls[0]["stream_options"] == {"include_usage": True}


# --- the factory decides which is which --------------------------------------------------------


def _gateway_with(monkeypatch: pytest.MonkeyPatch, **overrides) -> ModelGateway:
    monkeypatch.setattr(settings, "MODEL_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "MODEL_API_KEY", "sk-or-test")
    monkeypatch.setattr(settings, "MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "MODEL_ID", ROUTER_ID)
    monkeypatch.setattr(settings, "MODEL_ALLOWED_IDS", [ROUTER_ID])
    for name, value in overrides.items():
        monkeypatch.setattr(settings, name, value)
    return build_model_gateway()


def test_a_router_id_gets_the_retry_on_empty_flag(monkeypatch):
    """Without this the free router's empty answers stay fatal and the fix never reaches production."""
    gateway = _gateway_with(monkeypatch)

    assert gateway._provider._retry_on_empty is True


def test_a_fixed_id_does_not_get_the_flag(monkeypatch):
    """The whole point of the distinction: a named model must not be retried on an empty answer."""
    gateway = _gateway_with(
        monkeypatch, MODEL_ID=FIXED_ID, MODEL_ALLOWED_IDS=[FIXED_ID]
    )

    assert gateway._provider._retry_on_empty is False