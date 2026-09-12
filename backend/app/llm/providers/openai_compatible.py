"""OpenAI-compatible provider (Moonshot/Kimi, OpenAI, OpenRouter, local).

Moonshot's API is OpenAI-shaped, so one adapter covers it and any other OpenAI-compatible endpoint
selected by ``MODEL_BASE_URL`` (FR-072). This is the only module that imports the ``openai`` SDK.
"""

from app.llm.base import (
    ModelRequest,
    ModelResponse,
    ProviderPermanentError,
    ProviderTransientError,
    Usage,
)

_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str, name: str = "openai_compatible") -> None:
        from openai import AsyncOpenAI

        self.name = name
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, request: ModelRequest) -> ModelResponse:
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

        try:
            completion = await self._client.chat.completions.create(**kwargs)
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


def _map_error(exc: Exception) -> Exception:
    import openai

    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        return ProviderTransientError(str(exc))
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code in _TRANSIENT_STATUS:
            return ProviderTransientError(str(exc))
        return ProviderPermanentError(str(exc))
    return ProviderTransientError(str(exc))
