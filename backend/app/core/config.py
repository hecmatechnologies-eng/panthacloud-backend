from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "fussion-backend"
    APP_VERSION: str = "0.1.0"

    DATABASE_URL: str | None = None
    FALLBACK_SQLITE_URL: str = "sqlite+aiosqlite:///./fussion.db"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}

    @property
    def effective_database_url(self) -> str:
        """
        Determines the active database URL with strict environment checks.
        In production: PostgreSQL DATABASE_URL is strictly required.
        In development/test: Falls back to SQLite if PostgreSQL is unconfigured.
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
            return self.DATABASE_URL

        # Non-production (development, test)
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return self.FALLBACK_SQLITE_URL


settings = Settings()
