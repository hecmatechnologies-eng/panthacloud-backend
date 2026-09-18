"""Storage service factory and interface exports."""

from __future__ import annotations

from app.core.config import settings
from app.services.storage.base import StorageError, StorageNotFoundError, StorageProvider
from app.services.storage.local import LocalStorageProvider
from app.services.storage.r2 import R2StorageProvider

__all__ = [
    "LocalStorageProvider",
    "R2StorageProvider",
    "StorageError",
    "StorageNotFoundError",
    "StorageProvider",
    "get_storage_provider",
    "set_storage_provider",
]

_storage_provider: StorageProvider | None = None


def get_storage_provider() -> StorageProvider:
    """Return the configured StorageProvider instance.

    Uses R2StorageProvider if Cloudflare R2 credentials are configured;
    otherwise gracefully falls back to LocalStorageProvider.
    """
    global _storage_provider
    if _storage_provider is not None:
        return _storage_provider

    if settings.is_r2_configured:
        _storage_provider = R2StorageProvider(
            account_id=settings.R2_ACCOUNT_ID or "",
            access_key_id=settings.R2_ACCESS_KEY_ID or "",
            secret_access_key=settings.R2_SECRET_ACCESS_KEY or "",
            bucket_name=settings.R2_BUCKET_NAME,
            endpoint_url=settings.effective_r2_endpoint,
            public_url=settings.R2_PUBLIC_URL,
        )
    else:
        _storage_provider = LocalStorageProvider(settings.STORAGE_LOCAL_DIR)

    return _storage_provider


def set_storage_provider(provider: StorageProvider | None) -> None:
    """Explicitly set or reset the storage provider (used in testing)."""
    global _storage_provider
    _storage_provider = provider
