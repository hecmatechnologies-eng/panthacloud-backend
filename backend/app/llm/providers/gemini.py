"""Google Gemini adapter (FR-072, FR-125).

The only module that imports the vendor SDK. It maps Fussion's DTOs onto Gemini's API and Gemini's
errors onto the transient/permanent split the gateway retries on. It holds no policy — allowlists,
caps, budgets, retries and recording all live in the gateway.
"""

from app.llm.base import (
    ModelRequest,
    ModelResponse,
    ProviderPermanentError,
    ProviderTransientError,
    Usage,
)

# HTTP statuses worth retrying. 408/409 are transient races; 429 is rate limiting; 5xx is the
# vendor. Everything else is a request problem that will fail identically on retry.
_TRANSIENT_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class GeminiModelProvider:
    name = "gemini"

    def __init__(self, api_key: str, thinking_budget: int = 0) -> None:
        # Imported here, not at module scope: the app must start without the SDK when no provider
        # is configured, and tests must never import a vendor SDK.
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._thinking_budget = thinking_budget

    async def complete(self, request: ModelRequest) -> ModelResponse:
        from google.genai import types

        system_instruction = "\n\n".join(
            message.content for message in request.messages if message.role == "system"
        )
        contents = [
            types.Content(
                role="model" if message.role == "assistant" else "user",
                parts=[types.Part(text=message.content)],
            )
            for message in request.messages
            if message.role != "system"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_instruction or None,
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            # Disable thinking: it is billed as output but omitted from candidates_token_count,
            # so leaving it on both inflates cost and can starve the visible answer.
            thinking_config=types.ThinkingConfig(thinking_budget=self._thinking_budget),
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=request.model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise _map_error(exc) from exc

        try:
            text = response.text or ""
        except Exception:  # noqa: BLE001 — a blocked/safety response has no text
            text = ""
        if not text:
            raise ProviderPermanentError("Gemini returned no text content.")

        usage = response.usage_metadata
        return ModelResponse(
            text=text,
            model=request.model,
            provider=self.name,
            usage=Usage(
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            ),
        )


def _map_error(exc: Exception) -> Exception:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        if code in _TRANSIENT_STATUS:
            return ProviderTransientError(str(exc))
        return ProviderPermanentError(str(exc))
    # No HTTP status (connection reset, DNS, timeout): transient.
    return ProviderTransientError(str(exc))
