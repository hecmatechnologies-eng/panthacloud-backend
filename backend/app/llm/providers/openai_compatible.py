"""OpenAI-compatible provider (Moonshot/Kimi, OpenAI, OpenRouter, local).

Moonshot's API is OpenAI-shaped, so one adapter covers it and any other OpenAI-compatible endpoint
selected by ``MODEL_BASE_URL`` (FR-072). This is the only module that imports the ``openai`` SDK.
"""

from collections.abc import AsyncIterator

from app.llm.base import (
    ModelDelta,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ProviderPermanentError,
    ProviderTransientError,
    StreamDone,
    Usage,
)

_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        name: str = "openai_compatible",
        retry_on_empty: bool = False,
        client: object | None = None,
    ) -> None:
        """``client`` is an injection seam: this adapter had no tests, because constructing it built
        a real client and every path through it needed the network."""

        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        self.name = name
        self._client = client
        # Whether an empty completion should be retried. True only for router-style model ids, where
        # each call lands on a *different* underlying model: an empty answer is then a property of
        # the model that happened to be picked, and the retry is expected to select another. For a
        # fixed model an empty answer is a prompt or content problem, and retrying only repeats it.
        self._retry_on_empty = retry_on_empty

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            completion = await self._client.chat.completions.create(**self._kwargs(request))
        except Exception as exc:
            raise _map_error(exc) from exc

        choice = completion.choices[0] if completion.choices else None
        text = (choice.message.content or "") if choice is not None else ""
        if not text:
            raise self._empty_response_error()

        usage = completion.usage
        return ModelResponse(
            text=text,
            model=completion.model or request.model,
            provider=self.name,
            # Moonshot counts reasoning tokens inside completion_tokens, so this is the billed
            # output figure, not just the visible text.
            usage=Usage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            ),
        )

    def _kwargs(self, request: ModelRequest) -> dict:
        kwargs: dict = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": request.max_output_tokens,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        return kwargs

    def _empty_response_error(self) -> Exception:
        """A 200 whose body carries no answer.

        Routers get a transient error so the gateway retries and, if the chain allows, fails over:
        the next attempt lands on a different model and is likely to answer. Everyone else gets a
        permanent error, which is what this was before — a fixed model returning nothing will
        return nothing again, and the caller needs to be told that rather than left retrying.
        """
        if self._retry_on_empty:
            return ProviderTransientError("The model returned no text content.")
        return ProviderPermanentError("The model returned no text content.")

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Stream the reply. Usage is only sent by OpenAI-shaped APIs when it is asked for, and the
        ledger needs it, so ``stream_options`` is not optional here."""
        kwargs = self._kwargs(request) | {
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _map_error(exc) from exc

        parts: list[str] = []
        model = request.model
        usage = Usage(input_tokens=0, output_tokens=0)
        try:
            async for chunk in stream:
                if chunk.model:
                    model = chunk.model
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = Usage(
                        input_tokens=getattr(chunk_usage, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(chunk_usage, "completion_tokens", 0) or 0,
                    )
                # The usage-bearing chunk carries no choices, and a keepalive chunk carries neither.
                if not chunk.choices:
                    continue
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    parts.append(content)
                    yield ModelDelta(text=content)
        except Exception as exc:
            raise _map_error(exc) from exc

        if not parts and self._retry_on_empty:
            # Raised before StreamDone is yielded, so the gateway sees a failure and can retry while
            # nothing has been emitted. Without this the visitor is handed a silently empty message,
            # which reads as a broken widget rather than a retryable upstream blip.
            raise self._empty_response_error()

        yield StreamDone(
            text="".join(parts), model=model, provider=self.name, usage=usage
        )


def _map_error(exc: Exception) -> Exception:
    import openai

    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return ProviderTransientError(str(exc))
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code in _TRANSIENT_STATUS:
            return ProviderTransientError(str(exc))
        return ProviderPermanentError(str(exc))
    return ProviderTransientError(str(exc))
