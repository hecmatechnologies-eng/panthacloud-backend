"""The ``ModelProvider`` seam and its DTOs (FR-072).

Fussion's own types, deliberately not a vendor's. A provider adapter maps these to and from the
vendor API; swapping vendors is a new adapter, never a change to a caller.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ModelRequest:
    model: str
    messages: list[ModelMessage]
    max_output_tokens: int
    temperature: float | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str
    model: str
    provider: str
    usage: Usage


class ModelProvider(Protocol):
    """One vendor, reduced to a single call. ``stream`` arrives with B7."""

    name: str

    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class ModelProviderError(Exception):
    """Base for errors raised by a provider adapter."""


class ProviderTransientError(ModelProviderError):
    """Rate limit, timeout, or 5xx — the gateway may retry with backoff."""


class ProviderPermanentError(ModelProviderError):
    """Bad request, auth failure, or a 4xx that will not succeed on retry."""
