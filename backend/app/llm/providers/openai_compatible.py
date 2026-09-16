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
    def __init__(self, api_key: str, base_url: str, name: str = "openai_compatible") -> None:
        from openai import AsyncOpenAI

        self.name = name
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            completion = await self._client.chat.completions.create(**self._kwargs(request))
        except Exception as exc:
            raise _map_error(exc) from exc

        choice = completion.choices[0] if completion.choices else None
        text = (choice.message.content or "") if choice is not None else ""
        if not text:
            raise ProviderPermanentError("The model returned no text content.")

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
