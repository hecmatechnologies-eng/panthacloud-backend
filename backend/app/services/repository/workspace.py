import logging
import os
import shutil
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("fussion.workspace")


class SecurityViolationError(Exception):
    """Raised when an operation violates workspace containment or security boundaries."""


class WorkspaceLimitExceededError(Exception):
    """Raised when repository contents exceed configured resource thresholds."""


class WorkspaceManager:
    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.WORKSPACE_BASE_DIR).resolve()

    def get_workspace_path(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> Path:
        return (
            self.base_dir
            / str(organization_id)
            / str(project_id)
            / str(snapshot_id)
        ).resolve()

    def allocate_workspace(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> tuple[Path, str]:
        path = self.get_workspace_path(organization_id, project_id, snapshot_id)
        path.mkdir(parents=True, exist_ok=True)
        # Opaque reference token, never revealing the real server filesystem path
        workspace_ref = f"ws-{snapshot_id.hex[:16]}"
        return path, workspace_ref

    def assert_path_contained(self, workspace_path: Path, target_path: Path) -> Path:
        """
        Guarantees that target_path resolves strictly within workspace_path.
        Rejects directory traversal (../) and symlink escapes outside the workspace boundary.
        """
        real_workspace = workspace_path.resolve()
        
        # Check raw path traversal before resolving
        try:
            raw_target = (workspace_path / target_path).resolve()
        except (OSError, ValueError) as exc:
            raise SecurityViolationError(f"Invalid path representation: {exc}") from exc

        try:
            if not raw_target.is_relative_to(real_workspace):
                raise SecurityViolationError("Path traversal escape detected outside workspace boundary.")
        except AttributeError:
            # Fallback for older semantics
            if not str(raw_target).startswith(str(real_workspace)):
                raise SecurityViolationError("Path traversal escape detected outside workspace boundary.")

        # If the target path itself or any parent is a symlink pointing outside, reject
        curr = target_path if target_path.is_absolute() else workspace_path / target_path
        if curr.is_symlink():
            try:
                resolved_link = curr.resolve()
                if not resolved_link.is_relative_to(real_workspace):
                    raise SecurityViolationError("Symlink escape detected outside workspace boundary.")
            except (OSError, RuntimeError) as exc:
                raise SecurityViolationError(f"Unsafe symlink detected: {exc}") from exc

        return raw_target

    def check_workspace_limits(self, workspace_path: Path) -> None:
        """
        Validates directory depth, file count, file sizes, and cumulative repository size.
        """
        real_workspace = workspace_path.resolve()
        if not real_workspace.exists():
            return

        total_size_bytes = 0
        file_count = 0
        max_repo_bytes = settings.MAX_REPOSITORY_SIZE_MB * 1024 * 1024
        max_file_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

        for root, dirs, files in os.walk(real_workspace):
            root_path = Path(root)

            # Check directory depth relative to workspace root
            depth = len(root_path.relative_to(real_workspace).parts)
            if depth > settings.MAX_DIRECTORY_DEPTH:
                raise WorkspaceLimitExceededError(
                    f"Directory depth exceeded maximum limit ({settings.MAX_DIRECTORY_DEPTH})."
                )

            # Check symlink escapes on subdirectories
            for d in list(dirs):
                dir_path = root_path / d
                if dir_path.is_symlink():
                    try:
                        resolved_dir = dir_path.resolve()
                        if not resolved_dir.is_relative_to(real_workspace):
                            dirs.remove(d)  # Do not traverse unsafe directory symlinks
                    except (OSError, RuntimeError):
                        dirs.remove(d)

            for f in files:
                file_count += 1
                if file_count > settings.MAX_FILE_COUNT:
                    raise WorkspaceLimitExceededError(
                        f"File count exceeded maximum limit ({settings.MAX_FILE_COUNT})."
                    )

                file_path = root_path / f
                if file_path.is_symlink():
                    try:
                        resolved_file = file_path.resolve()
                        if not resolved_file.is_relative_to(real_workspace):
                            continue  # Skip unsafe symlink files
                    except (OSError, RuntimeError):
                        continue

                try:
                    f_size = file_path.stat().st_size
                    if f_size > max_file_bytes:
                        raise WorkspaceLimitExceededError(
                            f"File '{f}' exceeded maximum file size limit ({settings.MAX_FILE_SIZE_MB}MB)."
                        )
                    total_size_bytes += f_size
                    if total_size_bytes > max_repo_bytes:
                        raise WorkspaceLimitExceededError(
                            f"Total repository size exceeded maximum limit ({settings.MAX_REPOSITORY_SIZE_MB}MB)."
                        )
                except OSError:
                    continue

    def cleanup_workspace(self, workspace_path: Path) -> bool:
        """Safely removes an allocated workspace directory; returns True when it is gone.

        A workspace holds a cloned repository whose ``.git/config`` may embed a clone token, so a
        survivor is a credential left on disk. Teardown reports its own outcome rather than
        assuming success.
        """
        if not workspace_path.exists():
            return True

        # In Windows, read-only files (like .git objects) can cause rmtree to fail unless handled
        def on_rm_error(func, path, exc_info):
            try:
                os.chmod(path, 0o777)
                func(path)
            except (OSError, PermissionError):
                pass

        shutil.rmtree(workspace_path, onerror=on_rm_error)
        if workspace_path.exists():
            logger.warning("Workspace %s survived teardown and must be removed manually.", workspace_path)
            return False
        return True


workspace_manager = WorkspaceManager()
