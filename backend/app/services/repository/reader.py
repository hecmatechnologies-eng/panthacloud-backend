"""Repository read source for the agent's read tools (AGENT-ARCHITECTURE §7, §10).

The analyst reads the customer's real files from an isolated workspace — a shallow clone pinned to
a commit — not from the network. This module defines the read interface and a filesystem-backed
implementation; the tools depend on the interface, so a provider-backed reader can replace it.

Two safety rules hold on every path, in every method:

- containment: a ``../``, absolute or symlink path can never escape the workspace root;
- secrecy: VCS metadata, dependencies, build output, credentials and protected paths are never
  listed, read or searched. The workspace's ``.git/config`` carries the clone's access token, so a
  read tool that reached it would hand the model a credential (CLAUDE.md §4.2).
"""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.protected_paths import protected_reason
from app.services.repository.workspace import SecurityViolationError, WorkspaceManager

# Directories never worth listing, reading or searching: VCS metadata, dependencies and build
# output. Listing them wastes the analyst's context; reading them leaks secrets.
_IGNORED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".next",
        "dist",
        "build",
        "out",
        "coverage",
        "__pycache__",
        ".venv",
        "venv",
        ".turbo",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
    }
)

# Files that hold credentials and are never readable, in addition to `protected_reason`.
_DENIED_FILE_NAMES = frozenset(
    {".npmrc", ".netrc", ".htpasswd", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
)
_DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")

_MAX_SEARCH_FILE_BYTES = 1_000_000
_MAX_SEARCH_TOTAL_BYTES = 50_000_000


class RepositoryReaderError(Exception):
    """A read failure whose message is safe and useful to show the model."""


@dataclass(frozen=True, slots=True)
class TreeEntry:
    path: str
    entry_type: str  # "file"
    size: int


@dataclass(frozen=True, slots=True)
class TreeListing:
    entries: list[TreeEntry]
    total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class FileContent:
    path: str
    text: str
    start_line: int
    total_lines: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class SearchHit:
    path: str
    line_number: int
    line: str


@dataclass(frozen=True, slots=True)
class SearchResults:
    hits: list[SearchHit]
    total: int
    truncated: bool


class RepositoryReader(Protocol):
    async def list_tree(
        self, *, path: str, offset: int, max_entries: int
    ) -> TreeListing: ...

    async def read_file(self, *, path: str, offset: int, limit: int) -> FileContent: ...

    async def search(self, *, query: str, offset: int, max_results: int) -> SearchResults: ...


class LocalWorkspaceReader:
    """Reads a repository checked out into a local, containment-checked directory."""

    def __init__(self, root: Path, *, workspace_manager: WorkspaceManager | None = None) -> None:
        self._root = Path(root).resolve()
        self._workspace = workspace_manager or WorkspaceManager()

    async def list_tree(self, *, path: str = "", offset: int = 0, max_entries: int = 500) -> TreeListing:
        return await asyncio.to_thread(self._list_tree, path, offset, max_entries)

    async def read_file(self, *, path: str, offset: int = 0, limit: int = 200) -> FileContent:
        return await asyncio.to_thread(self._read_file, path, offset, limit)

    async def search(self, *, query: str, offset: int = 0, max_results: int = 50) -> SearchResults:
        return await asyncio.to_thread(self._search, query, offset, max_results)

    # --- synchronous implementation, offloaded off the event loop ---------------------------

    def _list_tree(self, path: str, offset: int, max_entries: int) -> TreeListing:
        base = self._resolve(path)
        if not base.exists() or not base.is_dir():
            raise RepositoryReaderError(f"Not a directory: {path or '.'}.")

        entries: list[TreeEntry] = []
        for current_root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if _normalize_part(d) not in _IGNORED_DIRS]
            current = Path(current_root)
            for name in files:
                file_path = current / name
                if file_path.is_symlink() or self._denied(file_path):
                    continue
                relative = file_path.relative_to(self._root).as_posix()
                entries.append(
                    TreeEntry(path=relative, entry_type="file", size=_safe_size(file_path))
                )
        entries.sort(key=lambda entry: entry.path)
        page = entries[offset : offset + max_entries]
        return TreeListing(
            entries=page, total=len(entries), truncated=offset + max_entries < len(entries)
        )

    def _read_file(self, path: str, offset: int, limit: int) -> FileContent:
        target = self._resolve(path)
        if not target.exists() or not target.is_file():
            raise RepositoryReaderError(f"File not found: {path}.")
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RepositoryReaderError(f"{path} is not a UTF-8 text file.") from exc
        except OSError as exc:
            # Never interpolate the OSError: it embeds the absolute workspace path.
            raise RepositoryReaderError(f"Could not read {path}.") from exc

        lines = text.splitlines()
        start = max(0, offset)
        end = start + limit
        return FileContent(
            path=path,
            text="\n".join(lines[start:end]),
            start_line=start + 1,
            total_lines=len(lines),
            truncated=end < len(lines),
        )

    def _search(self, query: str, offset: int, max_results: int) -> SearchResults:
        needle = query.lower()
        hits: list[SearchHit] = []
        bytes_scanned = 0
        for current_root, dirs, files in os.walk(self._root):
            dirs[:] = [d for d in dirs if _normalize_part(d) not in _IGNORED_DIRS]
            for name in files:
                file_path = Path(current_root) / name
                if file_path.is_symlink() or self._denied(file_path):
                    continue
                relative = file_path.relative_to(self._root).as_posix()
                size = _safe_size(file_path)
                if size > _MAX_SEARCH_FILE_BYTES:
                    continue
                if bytes_scanned + size > _MAX_SEARCH_TOTAL_BYTES:
                    page = hits[offset : offset + max_results]
                    return SearchResults(hits=page, total=len(hits), truncated=True)
                bytes_scanned += size
                try:
                    text = file_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if needle in line.lower():
                        hits.append(
                            SearchHit(
                                path=relative,
                                line_number=line_number,
                                line=line.strip()[:200],
                            )
                        )
        page = hits[offset : offset + max_results]
        return SearchResults(
            hits=page, total=len(hits), truncated=offset + max_results < len(hits)
        )

    def _resolve(self, path: str) -> Path:
        if not path:
            return self._root
        target = Path(path)
        if target.is_absolute():
            raise RepositoryReaderError("Path must be relative to the repository root.")
        if _is_denied(path):
            raise RepositoryReaderError(f"Refused path {path!r}: it is not readable.")
        try:
            resolved = self._workspace.assert_path_contained(self._root, target)
        except SecurityViolationError:
            # Never interpolate the exception: it can carry a raw OS path.
            raise RepositoryReaderError(f"Refused path {path!r}.") from None
        # Re-check after resolution: a symlinked or junctioned directory can point *inside* the
        # root at a denied location (a `vendor` link to `.git`), which containment alone allows.
        try:
            resolved_relative = resolved.relative_to(self._root).as_posix()
        except ValueError:
            raise RepositoryReaderError(f"Refused path {path!r}.") from None
        if _is_denied(resolved_relative):
            raise RepositoryReaderError(f"Refused path {path!r}: it is not readable.")
        return resolved

    def _denied(self, file_path: Path) -> bool:
        """Denial judged on the resolved target, so a link into `.git` cannot smuggle a read."""
        try:
            resolved = file_path.resolve()
            relative = resolved.relative_to(self._root).as_posix()
        except (OSError, ValueError):
            return True
        return _is_denied(relative)


def _normalize_part(part: str) -> str:
    # Windows strips trailing dots/spaces and folds case, so `.git.` and `.GIT` both reach `.git`.
    return part.rstrip(" .").lower()


def _is_denied(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    parts = [_normalize_part(part) for part in normalized.split("/") if part and part != "."]
    if any(part in _IGNORED_DIRS for part in parts):
        return True
    name = parts[-1] if parts else ""
    if name in _DENIED_FILE_NAMES or name.startswith(".env"):
        return True
    if name.endswith(_DENIED_SUFFIXES):
        return True
    return protected_reason(normalized) is not None


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
