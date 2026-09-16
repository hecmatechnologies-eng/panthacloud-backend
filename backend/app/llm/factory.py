"""Build the configured model provider and gateway from settings (FR-072).

The one place that decides which vendor adapter to instantiate. Unknown provider names fail loud:
a typo must not silently leave the runtime without a model. ``resolve_provider_config`` is the
single selector both the text provider and the agent adapter read, so adding a vendor is one edit.
"""

from dataclasses import dataclass

from app.core.config import Settings, settings
from app.llm.base import ModelProvider
from app.llm.gateway import ModelGateway

# Vendors whose API is OpenAI-shaped. Moonshot/Kimi is one; the base URL selects the host.
OPENAI_COMPATIBLE_PROVIDERS = frozenset(
    {"moonshot", "openai", "openrouter", "openai_compatible", "deepseek"}
)
DEFAULT_BASE_URLS = {
    "moonshot": "https://api.moonshot.ai/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """The vendor decision, shared by the text provider and the agent adapter."""

    kind: str  # "gemini" | "openai_compatible"
    model_id: str
    api_key: str
    base_url: str | None = None
    thinking_budget: int = 0


def resolve_provider_config(config: Settings | None = None) -> ProviderConfig:
    config = config or settings
    if config.MODEL_PROVIDER == "gemini":
        return ProviderConfig(
            kind="gemini",
            model_id=config.MODEL_ID,
            api_key=config.MODEL_API_KEY or "",
            thinking_budget=config.MODEL_THINKING_BUDGET,
        )
    if config.MODEL_PROVIDER in OPENAI_COMPATIBLE_PROVIDERS:
        base_url = config.MODEL_BASE_URL or DEFAULT_BASE_URLS.get(config.MODEL_PROVIDER)
        if not base_url:
            raise RuntimeError(
                f"MODEL_BASE_URL is required for MODEL_PROVIDER={config.MODEL_PROVIDER!r}."
            )
        return ProviderConfig(
            kind="openai_compatible",
            model_id=config.MODEL_ID,
            api_key=config.MODEL_API_KEY or "",
            base_url=base_url,
        )
    raise RuntimeError(f"Unknown MODEL_PROVIDER: {config.MODEL_PROVIDER!r}")


def build_model_gateway(config: Settings | None = None) -> ModelGateway | None:
    """Return a configured gateway, or ``None`` when no provider is configured.

    ``None`` is not a fallback: the runtime turns it into a 503 (CLAUDE.md §4.10).
    """
    config = config or settings
    if not config.MODEL_API_KEY:
        return None
    validate_model_configuration(config)
    return ModelGateway(_build_provider(config))


def validate_model_configuration(config: Settings | None = None) -> None:
    """Refuse an inconsistent model configuration at startup, not at the first request."""
    config = config or settings
    if config.MODEL_ID not in config.MODEL_ALLOWED_IDS:
        raise RuntimeError(
            f"MODEL_ID {config.MODEL_ID!r} is not in MODEL_ALLOWED_IDS "
            f"{config.MODEL_ALLOWED_IDS!r}; every model call would be refused."
        )
    if config.is_production and config.MODEL_DEFAULT_SPEND_LIMIT_USD is None:
        raise RuntimeError(
            "Production configuration error: MODEL_DEFAULT_SPEND_LIMIT_USD must be set. An "
            "uncapped organization is an unbounded cost event (AGENT-ARCHITECTURE §2)."
        )


def _build_provider(config: Settings) -> ModelProvider:
    provider = resolve_provider_config(config)
    if provider.kind == "gemini":
        from app.llm.providers.gemini import GeminiModelProvider

        return GeminiModelProvider(provider.api_key, thinking_budget=provider.thinking_budget)

    from app.llm.providers.openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        provider.api_key, provider.base_url or "", name=config.MODEL_PROVIDER
    )
