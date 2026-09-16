import hashlib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.dev_secrets import (
    ENCRYPTION_KEY_FIELD,
    JWT_SECRET_FIELD,
    load_or_create_dev_secrets,
)

# Anchored to the backend package, never to the working directory: CLAUDE.md §8 documents two
# different CWDs for the same installation (uvicorn and alembic from `backend/`, pytest from the
# repository root). A relative default would hand those two runs different keys, and every GitHub
# token encrypted under the first would silently stop decrypting.
DEFAULT_DEV_SECRETS_FILE = str(Path(__file__).resolve().parents[2] / ".dev-secrets.json")

# Environments that may generate their own development keys. Anything else — staging, an unset
# APP_ENV, a typo — is refused rather than quietly given a fresh random key per process: replicas
# would issue JWTs the next replica rejects, and ciphertext one wrote another cannot read.
_KEY_GENERATING_ENVIRONMENTS = frozenset({"development", "dev", "local", "test", "testing"})

# Placeholders that must never reach production, plus the two development values that leaked in
# baseline commit 1034f4a (CLAUDE.md §3.2). The leaked values are matched by SHA-256 so that
# removing them from source does not quietly remove the check that refuses them: they are
# compromised, and "it is only the dev key" stops being true the moment someone sets it in prod.
_WEAK_VALUES = frozenset({"secret", "changeme", "jwt_secret"})
_COMPROMISED_VALUE_HASHES = frozenset(
    {
        "59baa85cf45d5f57fc86b25e78cdd96e6c8940887c59c703d1f02812b2b21ef9",
        "742f2f565750b743459eadc634b20bd440b231f58f24bb12e23258e2e3b327a5",
    }
)


def _is_unacceptable(value: str) -> bool:
    return (
        value in _WEAK_VALUES
        or hashlib.sha256(value.encode()).hexdigest() in _COMPROMISED_VALUE_HASHES
    )


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "fussion-backend"
    APP_VERSION: str = "0.1.0"

    DATABASE_URL: str | None = None
    DEFAULT_POSTGRES_URL: str = "postgresql+psycopg://postgres:mwalimu_dev_2026@localhost:5432/fussion_db"
    FALLBACK_SQLITE_URL: str = "sqlite+aiosqlite:///./fussion.db"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    SECRET_ENCRYPTION_KEY: str | None = None
    # Development and test only: where this installation's generated keys live. Gitignored.
    DEV_SECRETS_FILE: str = DEFAULT_DEV_SECRETS_FILE

    # OAuth / SSO provider settings (Google, GitHub)
    GITHUB_OAUTH_CLIENT_ID: str | None = None
    GITHUB_OAUTH_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    OAUTH_STATE_EXPIRE_MINUTES: int = 10

    WORKSPACE_BASE_DIR: str = "./data/workspaces"
    MAX_REPOSITORY_SIZE_MB: int = 250
    MAX_FILE_SIZE_MB: int = 10
    MAX_FILE_COUNT: int = 10000
    MAX_DIRECTORY_DEPTH: int = 20
    ACQUISITION_TIMEOUT_SECONDS: int = 60
    INSPECTION_TIMEOUT_SECONDS: int = 30
    WORKSPACE_RETENTION_HOURS: int = 24

    # Runtime plane (step B). Rate limits are per-process fixed windows (app/runtime/rate_limit.py).
    PUBLIC_SESSION_TTL_HOURS: int = 24
    PUBLIC_CONVERSATION_RETENTION_DAYS: int = 30
    PUBLIC_CHAT_RATE_LIMIT_WINDOW_SECONDS: int = 60
    PUBLIC_CHAT_RATE_LIMIT_PER_IP: int = 60
    PUBLIC_CHAT_RATE_LIMIT_PER_INTEGRATION: int = 120
    PUBLIC_CHAT_RATE_LIMIT_PER_ORGANIZATION: int = 300
    PUBLIC_CHAT_RATE_LIMIT_PER_SESSION: int = 30

    # Model plane (step B5). No MODEL_API_KEY means no provider: the runtime returns 503 rather
    # than answering, and tests install a fake gateway explicitly.
    MODEL_PROVIDER: str = "gemini"
    MODEL_API_KEY: str | None = None
    # Required for OpenAI-compatible providers with no built-in default (app/llm/factory.py).
    MODEL_BASE_URL: str | None = None
    MODEL_ID: str = "gemini-2.5-flash"
    # Keep in step with app/llm/pricing.py: an allowed model with no price records zero cost.
    MODEL_ALLOWED_IDS: list[str] = ["gemini-2.5-flash"]
    # Gemini 2.5 "thinking" tokens are billed as output but are not reported in
    # candidates_token_count, so they silently inflate cost and can consume the output budget.
    # 0 disables thinking — the runtime is grounded Q&A, not reasoning.
    MODEL_THINKING_BUDGET: int = 0
    MODEL_MAX_INPUT_TOKENS: int = 20_000
    MODEL_MAX_OUTPUT_TOKENS: int = 1024
    MODEL_TIMEOUT_SECONDS: float = 30.0
    MODEL_MAX_RETRIES: int = 2
    MODEL_RETRY_BACKOFF_SECONDS: float = 0.5
    MODEL_HISTORY_MAX_MESSAGES: int = 20
    # Per-organization monthly spend budget (FR-074). None disables the budget; a non-positive
    # value suspends all calls. Fractions trigger warning, throttle and suspension.
    MODEL_DEFAULT_SPEND_LIMIT_USD: float | None = 10.0
    MODEL_BUDGET_WARNING_FRACTION: float = 0.8
    MODEL_BUDGET_THROTTLE_FRACTION: float = 0.95
    MODEL_BUDGET_THROTTLED_MAX_OUTPUT_TOKENS: int = 256

    # Embedding plane (step B6). "gemini" uses the real semantic embeddings; "deterministic" is the
    # lexical test/dev double. The dimension is stored on each KnowledgeBase, so a change here
    # affects only newly created bases.
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768
    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_SCORE_THRESHOLD: float = 0.0

    # Skills (step C). Defaults to the repository's skills/ tree beside the backend; override when
    # the backend is installed non-editable, where the default would not resolve.
    SKILLS_ROOT: str | None = None

    # GitHub App connection (step E). With no app configured, the install flow is unavailable and
    # the endpoints fail loud (503) rather than offering a button that cannot work. The private key
    # is a PEM secret; a value with literal "\n" is accepted and normalised when used.
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_PRIVATE_KEY: str | None = None
    GITHUB_APP_SLUG: str | None = None
    GITHUB_APP_CLIENT_ID: str | None = None
    GITHUB_APP_CLIENT_SECRET: str | None = None
    # The signed `state` that binds an install callback to the org and user that started it.
    GITHUB_APP_STATE_TTL_SECONDS: int = 600
    # Where the install callback sends the browser back to, after recording the installation.
    FRONTEND_URL: str = "http://localhost:3000"

    # Where a *customer's browser* reaches this API from (step B8). It is written into the loader
    # Fussion commits, so a wrong value ships a broken widget into a customer's repository.
    # Development falls back to the local API; production must set it (see `widget_script_url`).
    PUBLIC_API_URL: str | None = None
    # Auto-injected by Railway platform when a public domain is assigned.
    RAILWAY_PUBLIC_DOMAIN: str | None = None
    RAILWAY_STATIC_URL: str | None = None

    @property
    def widget_script_url(self) -> str:
        """The widget bundle's public URL, as a customer's browser will load it."""
        base = self.PUBLIC_API_URL
        if not base and self.RAILWAY_PUBLIC_DOMAIN:
            base = f"https://{self.RAILWAY_PUBLIC_DOMAIN}"
        elif not base and self.RAILWAY_STATIC_URL:
            base = f"https://{self.RAILWAY_STATIC_URL}"

        if not base:
            if self.is_production:
                raise RuntimeError(
                    "Production configuration error: PUBLIC_API_URL must be set (or RAILWAY_PUBLIC_DOMAIN available). "
                    "It is the origin a customer's browser loads the widget from and is written into every pull "
                    "request, so there is no default to fall back to."
                )
            base = "http://localhost:8000"
        return f"{base.rstrip('/')}/api/v1/public/widget.js"

    model_config = SettingsConfigDict(
        env_file=(
            str(Path(__file__).resolve().parents[2] / ".env"),
            str(Path(__file__).resolve().parents[3] / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}

    @property
    def may_generate_dev_keys(self) -> bool:
        return self.APP_ENV.lower() in _KEY_GENERATING_ENVIRONMENTS

    @property
    def effective_jwt_secret_key(self) -> str:
        if self.is_production:
            if not self.JWT_SECRET_KEY or _is_unacceptable(self.JWT_SECRET_KEY):
                raise RuntimeError(
                    "Production configuration error: JWT_SECRET_KEY must be configured in "
                    "production. Empty, placeholder and known-compromised values are refused, and "
                    "there is no development fallback. Use a long random value."
                )
            return self.JWT_SECRET_KEY
        return self.JWT_SECRET_KEY or self._dev_secret(JWT_SECRET_FIELD)

    @property
    def effective_secret_encryption_key(self) -> str:
        if self.is_production:
            if not self.SECRET_ENCRYPTION_KEY or _is_unacceptable(self.SECRET_ENCRYPTION_KEY):
                raise RuntimeError(
                    "Production configuration error: SECRET_ENCRYPTION_KEY must be configured in "
                    "production. Empty, placeholder and known-compromised values are refused, and "
                    "there is no development fallback. Generate one with Fernet.generate_key()."
                )
            return self.SECRET_ENCRYPTION_KEY
        return self.SECRET_ENCRYPTION_KEY or self._dev_secret(ENCRYPTION_KEY_FIELD)

    def _dev_secret(self, field: str) -> str:
        """Read one key from this installation's generated development secrets file.

        Never reached in production, and only reached at all when the environment does not supply
        the value. Any environment outside `_KEY_GENERATING_ENVIRONMENTS` is refused instead of
        being handed a per-process random key.
        """
        if not self.may_generate_dev_keys:
            raise RuntimeError(
                f"Configuration error: APP_ENV={self.APP_ENV!r} must supply JWT_SECRET_KEY and "
                "SECRET_ENCRYPTION_KEY explicitly. Keys are generated only for "
                f"{sorted(_KEY_GENERATING_ENVIRONMENTS)}, because a generated key differs per "
                "process: tokens and stored ciphertext would not survive a restart or a second "
                "replica."
            )
        return load_or_create_dev_secrets(self.DEV_SECRETS_FILE)[field]



    @staticmethod
    def _normalize_database_url(url: str) -> str:
        """Normalize database URL for async SQLAlchemy with psycopg3.

        Railway and other PaaS inject connection strings starting with `postgresql://` or `postgres://`.
        SQLAlchemy 2.0 async with psycopg 3 requires `postgresql+psycopg://`.
        """
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def effective_database_url(self) -> str:
        """
        Determines the active database URL with strict environment checks.
        In production: PostgreSQL DATABASE_URL is strictly required.
        In test: Isolated SQLite test database is used.
        In development/default: PostgreSQL is the default database.
        """
        if self.is_production:
            if not self.DATABASE_URL:
                raise RuntimeError(
                    "Production configuration error: DATABASE_URL must be specified. "
                    "Silent fallback to SQLite is prohibited in production."
                )
            if "sqlite" in self.DATABASE_URL.lower():
                raise RuntimeError(
                    "Production configuration error: SQLite is not permitted in production. "
                    "PostgreSQL is the mandatory system of record."
                )
            return self._normalize_database_url(self.DATABASE_URL)

        # Test environment uses isolated test database
        if self.APP_ENV.lower() in {"test", "testing"}:
            if self.DATABASE_URL and "sqlite" in self.DATABASE_URL.lower():
                return self.DATABASE_URL
            return self.FALLBACK_SQLITE_URL

        # Non-production (development, default)
        if self.DATABASE_URL:
            return self._normalize_database_url(self.DATABASE_URL)
        return self._normalize_database_url(self.DEFAULT_POSTGRES_URL)


settings = Settings()
