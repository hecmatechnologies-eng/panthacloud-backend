"""Deterministic model provider for tests (CLAUDE.md §6, FIRST).

No network, no paid API, no nondeterminism. It records the requests it received so a test can
assert on the assembled prompt, and can be made to fail on demand so the gateway's error and retry
paths are testable.
"""

from app.llm.base import ModelRequest, ModelResponse, Usage


class FakeModelProvider:
    name = "fake"

    def __init__(
        self,
        reply: str = "Test reply from the model.",
        usage: Usage | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reply = reply
        self.usage = usage if usage is not None else Usage(input_tokens=10, output_tokens=5)
        self.error = error
        self.calls: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return ModelResponse(
            text=self.reply,
            model=request.model,
            provider=self.name,
            usage=self.usage,
        )
