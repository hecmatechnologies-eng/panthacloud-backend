"""Shallow-clone a website integration's repository at a pinned revision (step C10).

The analyst reads real files from an isolated workspace. The clone is depth-1, at the integration's
default branch; the commit SHA is resolved immediately so the analysis is bound to an immutable
revision. Git output is sanitized so a token can never reach a log.

Git runs through `asyncio.to_thread`, not `asyncio.create_subprocess_exec`. The development server
installs Windows' SelectorEventLoop because psycopg's async driver cannot use Proactor (`run_dev.py`,
CLAUDE.md §8), and the selector loop has no subprocess transport on Windows: `create_subprocess_exec`
raises `NotImplementedError` there, which turned every analysis into an unhandled 500. A blocking
`subprocess.run` in a worker thread behaves identically under every loop and on every platform, so the
dev server and production exercise the same code.
"""

import asyncio
import subprocess
from pathlib import Path

from app.core.config import settings
from app.models.website_integration import WebsiteIntegration
from app.services.repository.acquisition import sanitize_git_output


class RepositoryCloneError(Exception):
    """The repository could not be cloned or its revision resolved."""


def clone_url_for(integration: WebsiteIntegration, token: str | None) -> str:
    owner = integration.repository_owner
    name = integration.repository_name
    if token:
        return f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    return f"https://github.com/{owner}/{name}.git"


async def _git(
    *args: str, cwd: Path | None = None, timeout_message: str
) -> subprocess.CompletedProcess[bytes]:
    """Run ``git`` off the event loop, mapping its timeout onto the builtin `TimeoutError`."""

    def _invoke() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            timeout=float(settings.ACQUISITION_TIMEOUT_SECONDS),
            check=False,
        )

    try:
        return await asyncio.to_thread(_invoke)
    except subprocess.TimeoutExpired:
        raise TimeoutError(timeout_message) from None


async def clone_repository(clone_url: str, branch: str, workspace_path: Path) -> str:
    """Clone ``clone_url`` at ``branch`` into ``workspace_path``; return the pinned commit SHA."""
    clone = await _git(
        "clone",
        "--depth",
        "1",
        "--branch",
        branch,
        clone_url,
        str(workspace_path),
        timeout_message=(
            f"Repository clone timed out after {settings.ACQUISITION_TIMEOUT_SECONDS} seconds."
        ),
    )
    if clone.returncode != 0:
        raise RepositoryCloneError(
            "Git clone failed: " + sanitize_git_output(clone.stderr.decode("utf-8", errors="replace"))
        )

    rev = await _git(
        "rev-parse",
        "HEAD",
        cwd=workspace_path,
        timeout_message="Timed out resolving the cloned commit SHA.",
    )
    if rev.returncode != 0:
        raise RepositoryCloneError("Failed to resolve the cloned commit SHA.")
    return rev.stdout.decode("utf-8").strip()
