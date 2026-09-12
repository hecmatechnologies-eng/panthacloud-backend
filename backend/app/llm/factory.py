"""Build the configured ``ModelGateway`` from settings (FR-072).

The one place that decides which vendor adapter to instantiate. Unknown provider names fail loud:
a typo must not silently leave the runtime without a model.
"""

from app.core.config import Settings, settings
from app.llm.base import ModelProvider
from app.llm.gateway import ModelGateway

# Vendors whose API is OpenAI-shaped. Moonshot/Kimi is one; the base URL selects the host.
_OPENAI_COMPATIBLE_PROVIDERS = frozenset({"moonshot", "openai", "openrouter", "openai_compatible"})
_DEFAULT_BASE_URLS = {
    "moonshot": "https://api.moonshot.ai/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


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
    if config.MODEL_PROVIDER == "gemini":
        from app.llm.providers.gemini import GeminiModelProvider

        return GeminiModelProvider(
            config.MODEL_API_KEY or "", thinking_budget=config.MODEL_THINKING_BUDGET
        )
    if config.MODEL_PROVIDER in _OPENAI_COMPATIBLE_PROVIDERS:
        from app.llm.providers.openai_compatible import OpenAICompatibleProvider

        base_url = config.MODEL_BASE_URL or _DEFAULT_BASE_URLS.get(config.MODEL_PROVIDER)
        if not base_url:
            raise RuntimeError(
                f"MODEL_BASE_URL is required for MODEL_PROVIDER={config.MODEL_PROVIDER!r}."
            )
        return OpenAICompatibleProvider(
            config.MODEL_API_KEY or "", base_url, name=config.MODEL_PROVIDER
        )
    raise RuntimeError(f"Unknown MODEL_PROVIDER: {config.MODEL_PROVIDER!r}")
