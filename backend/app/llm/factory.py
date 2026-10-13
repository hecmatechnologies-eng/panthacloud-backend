"""Build the configured model provider and gateway from settings (FR-072).

The one place that decides which vendor adapter to instantiate. Unknown provider names fail loud:
a typo must not silently leave the runtime without a model. ``resolve_provider_config`` is the
single selector both the text provider and the agent adapter read, so adding a vendor is one edit.

It also assembles the optional *fallback* provider, consulted by the gateway only when the primary
is transiently unavailable. That exists because a single quota is a single point of failure for a
product whose whole job is unattended repository analysis: when the primary's daily allowance is
gone at 03:00, a weaker model answering is worth more than a 500 and a stopped pipeline.
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

# Model ids that select a different underlying model per request rather than naming one model.
#
# Only these get an empty completion treated as retryable: an empty answer is then a property of the
# model that happened to be picked, and the next attempt lands on another one. An *explicit* list,
# because the alternative is guessing from the id — and a wrong guess either retries a genuinely
# hopeless request or gives up on one that would have answered.
_ROUTER_MODEL_IDS = frozenset({"openrouter/free"})


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
    return _resolve(
        provider=config.MODEL_PROVIDER,
        api_key=config.MODEL_API_KEY or "",
        base_url=config.MODEL_BASE_URL,
        model_id=config.MODEL_ID,
        thinking_budget=config.MODEL_THINKING_BUDGET,
    )


def _resolve(
    *, provider: str, api_key: str, base_url: str | None, model_id: str, thinking_budget: int
) -> ProviderConfig:
    """The vendor decision for one provider, from explicit values rather than settings.

    Shared by the primary and the fallback so both take the same set of vendor names and the same
    base-URL defaults. Duplicating this would be the same bug twice: a fallback that recognised
    fewer vendors than the primary, discovered when the failover was needed.
    """
    if provider == "gemini":
        return ProviderConfig(
            kind="gemini",
            model_id=model_id,
            api_key=api_key,
            thinking_budget=thinking_budget,
        )
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        resolved_base_url = base_url or DEFAULT_BASE_URLS.get(provider)
        if not resolved_base_url:
            raise RuntimeError(
                f"MODEL_BASE_URL is required for MODEL_PROVIDER={provider!r}."
            )
        return ProviderConfig(
            kind="openai_compatible",
            model_id=model_id,
            api_key=api_key,
            base_url=resolved_base_url,
        )
    raise RuntimeError(f"Unknown MODEL_PROVIDER: {provider!r}")


def build_model_gateway(config: Settings | None = None) -> ModelGateway | None:
    """Return a configured gateway, or ``None`` when no provider is configured.

    ``None`` is not a fallback: the runtime turns it into a 503 (CLAUDE.md §4.10).
    """
    config = config or settings
    if not config.MODEL_API_KEY:
        return None
    validate_model_configuration(config)
    provider = _build_provider(resolve_provider_config(config), name=config.MODEL_PROVIDER)
    fallback, fallback_model = _build_fallback(config)
    return ModelGateway(provider, fallback=fallback, fallback_model=fallback_model)


def _build_fallback(config: Settings) -> tuple[ModelProvider | None, str | None]:
    """The secondary provider, or ``(None, None)`` when failover is not configured.

    Keyed on the key alone, so setting ``MODEL_FALLBACK_API_KEY`` is the single switch that turns
    the behaviour on — a provider name without a key cannot authenticate, and a key without a
    provider name has no vendor to resolve, which is raised rather than guessed.
    """
    if not config.MODEL_FALLBACK_API_KEY:
        return None, None
    if not config.MODEL_FALLBACK_PROVIDER:
        raise RuntimeError(
            "MODEL_FALLBACK_PROVIDER is required when MODEL_FALLBACK_API_KEY is set; "
            "there is no default vendor for a failover."
        )
    provider_config = _resolve(
        provider=config.MODEL_FALLBACK_PROVIDER,
        api_key=config.MODEL_FALLBACK_API_KEY,
        base_url=config.MODEL_FALLBACK_BASE_URL,
        model_id=config.MODEL_FALLBACK_ID,
        # The fallback carries no thinking budget: it exists to answer, not to reason, and a
        # thinking budget the operator never configured must not silently apply to it.
        thinking_budget=0,
    )
    provider = _build_provider(provider_config, name=config.MODEL_FALLBACK_PROVIDER)
    return provider, config.MODEL_FALLBACK_ID


def validate_model_configuration(config: Settings | None = None) -> None:
    """Refuse an inconsistent model configuration at startup, not at the first request."""
    config = config or settings
    if config.MODEL_ID not in config.MODEL_ALLOWED_IDS:
        raise RuntimeError(
            f"MODEL_ID {config.MODEL_ID!r} is not in MODEL_ALLOWED_IDS "
            f"{config.MODEL_ALLOWED_IDS!r}; every model call would be refused."
        )
    if config.MODEL_FALLBACK_API_KEY and config.MODEL_FALLBACK_ID not in config.MODEL_FALLBACK_ALLOWED_IDS:
        raise RuntimeError(
            f"MODEL_FALLBACK_ID {config.MODEL_FALLBACK_ID!r} is not in MODEL_FALLBACK_ALLOWED_IDS "
            f"{config.MODEL_FALLBACK_ALLOWED_IDS!r}. The fallback bypasses the caller's allowlist "
            f"by construction, so this list is the only thing standing between an operator typo and "
            f"traffic being sent to an unvetted model."
        )
    if config.is_production and config.MODEL_DEFAULT_SPEND_LIMIT_USD is None:
        raise RuntimeError(
            "Production configuration error: MODEL_DEFAULT_SPEND_LIMIT_USD must be set. An "
            "uncapped organization is an unbounded cost event (AGENT-ARCHITECTURE §2)."
        )


def _build_provider(provider: ProviderConfig, *, name: str) -> ModelProvider:
    """Instantiate the adapter for one resolved provider config.

    Takes the config rather than ``Settings`` so the primary and the fallback share this, and takes
    the vendor name explicitly because it is recorded on every usage row — deriving it from the
    global ``MODEL_PROVIDER`` would stamp every fallback call as "gemini".
    """
    if provider.kind == "gemini":
        from app.llm.providers.gemini import GeminiModelProvider

        return GeminiModelProvider(provider.api_key, thinking_budget=provider.thinking_budget)

    from app.llm.providers.openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        provider.api_key,
        provider.base_url or "",
        name=name,
        retry_on_empty=provider.model_id in _ROUTER_MODEL_IDS,
    )
