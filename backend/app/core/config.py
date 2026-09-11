from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "fussion-backend"
    APP_VERSION: str = "0.1.0"

    DATABASE_URL: str | None = None
    FALLBACK_SQLITE_URL: str = "sqlite+aiosqlite:///./fussion.db"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    JWT_SECRET_KEY: str | None = None
    JWT_DEV_SECRET: str = "***REMOVED***"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    SECRET_ENCRYPTION_KEY: str | None = None
    SECRET_DEV_ENCRYPTION_KEY: str = "***REMOVED***="

    WORKSPACE_BASE_DIR: str = "./data/workspaces"
    MAX_REPOSITORY_SIZE_MB: int = 250
    MAX_FILE_SIZE_MB: int = 10
    MAX_FILE_COUNT: int = 10000
    MAX_DIRECTORY_DEPTH: int = 20
    ACQUISITION_TIMEOUT_SECONDS: int = 60
    INSPECTION_TIMEOUT_SECONDS: int = 30
    WORKSPACE_RETENTION_HOURS: int = 24

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}

    @property
    def effective_jwt_secret_key(self) -> str:
        if self.is_production:
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in {
                "secret",
                "changeme",
                "jwt_secret",
                self.JWT_DEV_SECRET,
            }:
                raise RuntimeError(
                    "Production configuration error: A secure, high-entropy JWT_SECRET_KEY "
                    "must be configured in production. Falling back to default secrets is prohibited."
                )
            return self.JWT_SECRET_KEY
        return self.JWT_SECRET_KEY or self.JWT_DEV_SECRET

    @property
    def effective_secret_encryption_key(self) -> str:
        if self.is_production:
            if not self.SECRET_ENCRYPTION_KEY or self.SECRET_ENCRYPTION_KEY in {
                "secret",
                "changeme",
                self.SECRET_DEV_ENCRYPTION_KEY,
            }:
                raise RuntimeError(
                    "Production configuration error: A secure SECRET_ENCRYPTION_KEY must be configured in production. "
                    "Falling back to dev encryption keys is strictly prohibited."
                )
            return self.SECRET_ENCRYPTION_KEY
        return self.SECRET_ENCRYPTION_KEY or self.SECRET_DEV_ENCRYPTION_KEY



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
