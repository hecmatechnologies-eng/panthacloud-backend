"""Shallow-clone a website integration's repository at a pinned revision (step C10).

The analyst reads real files from an isolated workspace. The clone is depth-1, at the integration's
default branch; the commit SHA is resolved immediately so the analysis is bound to an immutable
revision. Git output is sanitized so a token can never reach a log.

Git runs through `app.services.repository.git_command.run_git` — a blocking `subprocess.run` in a
worker thread rather than `asyncio.create_subprocess_exec`. The development server installs Windows'
SelectorEventLoop (psycopg's async driver cannot use Proactor — `run_dev.py`, CLAUDE.md §8), and that
loop has no subprocess transport on Windows, so `create_subprocess_exec` raises
`NotImplementedError`, which turned every analysis into an unhandled 500.
"""

from pathlib import Path

from app.core.config import settings
from app.models.website_integration import WebsiteIntegration
from app.services.repository.acquisition import sanitize_git_output
from app.services.repository.git_command import run_git


class RepositoryCloneError(Exception):
    """The repository could not be cloned or its revision resolved."""


def clone_url_for(integration: WebsiteIntegration, token: str | None) -> str:
    owner = integration.repository_owner
    name = integration.repository_name
    if token:
        return f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    return f"https://github.com/{owner}/{name}.git"


async def clone_repository(clone_url: str, branch: str, workspace_path: Path) -> str:
    """Clone ``clone_url`` at ``branch`` into ``workspace_path``; return the pinned commit SHA."""
    # First attempt: blobless shallow clone for 5-10x faster acquisition
    clone = await run_git(
        ["clone", "--depth", "1", "--filter=blob:none", "--branch", branch, clone_url, str(workspace_path)],
        timeout_seconds=float(settings.ACQUISITION_TIMEOUT_SECONDS),
        timeout_message=(
            f"Repository clone timed out after {settings.ACQUISITION_TIMEOUT_SECONDS} seconds."
        ),
    )
    if clone.returncode != 0:
        # Fallback to standard shallow clone if server or protocol rejects blobless filtering
        if workspace_path.exists():
            import shutil

            shutil.rmtree(workspace_path, ignore_errors=True)
        clone = await run_git(
            ["clone", "--depth", "1", "--branch", branch, clone_url, str(workspace_path)],
            timeout_seconds=float(settings.ACQUISITION_TIMEOUT_SECONDS),
            timeout_message=(
                f"Repository clone timed out after {settings.ACQUISITION_TIMEOUT_SECONDS} seconds."
            ),
        )

    if clone.returncode != 0:
        raise RepositoryCloneError(
            "Git clone failed: " + sanitize_git_output(clone.stderr.decode("utf-8", errors="replace"))
        )

    rev = await run_git(
        ["rev-parse", "HEAD"],
        cwd=workspace_path,
        timeout_seconds=float(settings.ACQUISITION_TIMEOUT_SECONDS),
        timeout_message="Timed out resolving the cloned commit SHA.",
    )
    if rev.returncode != 0:
        raise RepositoryCloneError("Failed to resolve the cloned commit SHA.")
    return rev.stdout.decode("utf-8").strip()
