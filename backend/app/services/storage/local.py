"""Local filesystem Storage Provider.

Used as a deterministic, zero-external-dependency fallback for local development
and automated test suites. Offloads filesystem I/O to the dedicated thread pool.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.repository.executor import run_in_io_thread
from app.services.storage.base import StorageError, StorageNotFoundError, StorageProvider

logger = logging.getLogger("fussion.storage.local")


class LocalStorageProvider(StorageProvider):
    """Filesystem-backed storage provider with strict path containment."""

    def __init__(self, base_dir: str | Path = "./data/storage") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        """Resolve and verify that the target path does not escape the storage base directory."""
        clean_key = key.lstrip("/\\")
        target = (self.base_dir / clean_key).resolve()
        try:
            target.relative_to(self.base_dir)
        except ValueError as exc:
            raise StorageError(f"Path traversal detected for storage key: {key}") from exc
        return target

    def _sync_upload(self, key: str, data: bytes) -> str:
        target = self._resolve_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rel = target.relative_to(self.base_dir).as_posix()
        return f"local://{rel}"

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        return await run_in_io_thread(self._sync_upload, key, data)

    def _sync_download(self, key: str) -> bytes:
        target = self._resolve_path(key)
        if not target.is_file():
            raise StorageNotFoundError(f"Local storage object {key} not found")
        return target.read_bytes()

    async def download(self, key: str) -> bytes:
        return await run_in_io_thread(self._sync_download, key)

    def _sync_delete(self, key: str) -> None:
        target = self._resolve_path(key)
        if target.is_file():
            target.unlink(missing_ok=True)
            # Prune empty parent dirs up to base_dir
            parent = target.parent
            while parent != self.base_dir and parent.is_dir():
                try:
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
                    else:
                        break
                except OSError:
                    break

    async def delete(self, key: str) -> None:
        await run_in_io_thread(self._sync_delete, key)

    def _sync_exists(self, key: str) -> bool:
        target = self._resolve_path(key)
        return target.is_file()

    async def exists(self, key: str) -> bool:
        return await run_in_io_thread(self._sync_exists, key)

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        target = self._resolve_path(key)
        rel = target.relative_to(self.base_dir).as_posix()
        return f"/api/v1/storage/files/{rel}"
