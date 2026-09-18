import os
import re
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import settings

WINDOWS_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


class SandboxError(Exception):
    """Base exception for all sandbox errors."""


class SandboxSecurityError(SandboxError):
    """Raised when a sandbox file operation violates containment or path rules."""


class SandboxLimitExceededError(SandboxError):
    """Raised when sandbox resource limits are exceeded."""


class SandboxNotSupportedError(SandboxError):
    """Raised when code execution is requested but no sandbox backend exists (CLAUDE.md §4.6)."""


@dataclass(frozen=True)
class SandboxResult:
    """The outcome of executing a command in a sandbox."""

    exit_code: int
    stdout: str
    stderr: str


@runtime_checkable
class SandboxProvider(Protocol):
    """Executes a command in an isolated sandbox.

    No backend implements this: nothing executes customer code on the control plane
    (CLAUDE.md §4.6). The Protocol is defined now so a container-backed implementation is a
    drop-in later; until then the workspace provider refuses rather than pretending to run.
    """

    def run(
        self,
        workspace_path: Path,
        command: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> SandboxResult: ...


class LocalWorkspaceProvider:
    """A per-run, path-checked file workspace — **not** a sandbox.

    It provides containment and resource limits for Fussion's own file writes, and no process,
    filesystem or network isolation. It therefore refuses `run()`: executing customer code needs a
    container-backed `SandboxProvider`, which does not exist yet (CLAUDE.md §2, §4.6).
    """

    def __init__(self, base_dir: str | None = None) -> None:
        root = Path(base_dir or settings.WORKSPACE_BASE_DIR).resolve()
        self.base_dir = (root / "sandboxes").resolve()

    def run(
        self,
        workspace_path: Path,
        command: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> SandboxResult:
        """Refuse: Fussion does not execute customer code on the control plane (CLAUDE.md §4.6)."""
        del workspace_path, command, timeout_seconds
        raise SandboxNotSupportedError(
            "No sandbox backend is configured. Fussion does not execute customer code on the "
            "control plane; a container-backed SandboxProvider is required."
        )

    def get_sandbox_path(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> Path:
        return (
            self.base_dir
            / str(organization_id)
            / str(project_id)
            / str(run_id)
        ).resolve()

    def allocate(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> tuple[Path, str]:
        path = self.get_sandbox_path(organization_id, project_id, run_id)
        path.mkdir(parents=True, exist_ok=True)
        sandbox_ref = f"sbx-{run_id.hex[:16]}"
        return path, sandbox_ref

    def assert_path_contained(self, sandbox_path: Path, target_path: str | Path) -> Path:
        """
        Guarantees that target_path resolves strictly within sandbox_path.
        Rejects directory traversal (../), absolute paths, Windows device paths, UNC paths, and symlink escapes.
        """
        raw_str = str(target_path).strip()

        # Reject null bytes
        if "\0" in raw_str:
            raise SandboxSecurityError("Null bytes detected in path.")

        # Reject absolute paths (UNIX leading slash or Windows drive letter)
        if raw_str.startswith(("/", "\\")):
            raise SandboxSecurityError(f"Absolute path '{raw_str}' is forbidden.")
        if re.match(r"^[a-zA-Z]:", raw_str):
            raise SandboxSecurityError(f"Drive letter path '{raw_str}' is forbidden.")

        # Reject Windows device names
        parts = Path(raw_str).parts
        for part in parts:
            clean_part = part.split(".")[0].upper()
            if clean_part in WINDOWS_DEVICE_NAMES:
                raise SandboxSecurityError(f"Windows device path '{part}' is forbidden.")

        # Normalization and containment check
        real_sandbox = sandbox_path.resolve()
        try:
            resolved_target = (sandbox_path / raw_str).resolve()
        except (OSError, ValueError) as exc:
            raise SandboxSecurityError(f"Invalid path structure: {exc}") from exc

        # Must be relative to real_sandbox
        try:
            if not resolved_target.is_relative_to(real_sandbox):
                raise SandboxSecurityError(f"Path traversal detected: '{raw_str}' escapes sandbox.")
        except AttributeError:
            if not str(resolved_target).startswith(str(real_sandbox)):
                raise SandboxSecurityError(f"Path traversal detected: '{raw_str}' escapes sandbox.")

        # Check symlink escape
        curr = Path(raw_str) if Path(raw_str).is_absolute() else sandbox_path / raw_str
        if curr.is_symlink():
            try:
                resolved_link = curr.resolve()
                if not resolved_link.is_relative_to(real_sandbox):
                    raise SandboxSecurityError("Symlink escape detected.")
            except (OSError, RuntimeError) as exc:
                raise SandboxSecurityError(f"Unsafe symlink detected: {exc}") from exc

        return resolved_target

    def write_file(self, sandbox_path: Path, rel_path: str, content: str) -> Path:
        resolved = self.assert_path_contained(sandbox_path, rel_path)
        # Check size limit (max 10MB)
        if len(content.encode("utf-8")) > 10 * 1024 * 1024:
            raise SandboxLimitExceededError("File size exceeds 10MB limit.")

        resolved.parent.mkdir(parents=True, exist_ok=True)
        # newline="": write the exact line endings, so a CRLF file does not become \r\r\n.
        resolved.write_text(content, encoding="utf-8", newline="")
        return resolved

    def read_file(self, sandbox_path: Path, rel_path: str) -> str:
        resolved = self.assert_path_contained(sandbox_path, rel_path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"File '{rel_path}' not found in sandbox.")
        with resolved.open(encoding="utf-8", newline="") as handle:
            return handle.read()

    def create_file(self, sandbox_path: Path, rel_path: str, content: str) -> Path:
        return self.write_file(sandbox_path, rel_path, content)

    def modify_file(self, sandbox_path: Path, rel_path: str, content: str) -> Path:
        resolved = self.assert_path_contained(sandbox_path, rel_path)
        if not resolved.exists():
            raise FileNotFoundError(f"Cannot modify nonexistent file '{rel_path}'.")
        return self.write_file(sandbox_path, rel_path, content)

    def list_files(self, sandbox_path: Path) -> list[str]:
        real_sandbox = sandbox_path.resolve()
        if not real_sandbox.exists():
            return []
        results = []
        for root, _, files in os.walk(real_sandbox):
            root_p = Path(root)
            for f in files:
                full_p = root_p / f
                rel_p = full_p.relative_to(real_sandbox).as_posix()
                results.append(rel_p)
        return sorted(results)

    def cleanup(self, sandbox_path: Path) -> None:
        real_sandbox = sandbox_path.resolve()
        if real_sandbox.exists():
            shutil.rmtree(real_sandbox, ignore_errors=True)


workspace_provider = LocalWorkspaceProvider()

