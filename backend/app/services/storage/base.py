"""Abstract Storage Provider seam (Cloudflare R2 / S3-compatible and local fallback).

Separates file storage from document ingestion and parsing logic, adhering to the
Single Responsibility and Open/Closed principles.
"""

from __future__ import annotations

import abc


class StorageError(Exception):
    """Base exception for object storage operations."""


class StorageNotFoundError(StorageError):
    """Raised when an object key is not found in storage."""


class StorageProvider(abc.ABC):
    """Abstract interface for object storage operations."""

    @abc.abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload data to storage under the specified key.

        Returns a storage reference or URL.
        """
        ...

    @abc.abstractmethod
    async def download(self, key: str) -> bytes:
        """Download raw bytes for the specified key.

        Raises StorageNotFoundError if the key does not exist.
        """
        ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Delete object under the specified key.

        Idempotent: does not raise if the key is already absent.
        """
        ...

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if the object key exists in storage."""
        ...

    @abc.abstractmethod
    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Return an accessible URL (e.g. presigned or direct) for authorized retrieval."""
        ...
