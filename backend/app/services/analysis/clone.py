"""Shallow-clone a website integration's repository at a pinned revision (step C10).

The analyst reads real files from an isolated workspace. The clone is depth-1, at the integration's
default branch; the commit SHA is resolved immediately so the analysis is bound to an immutable
revision. Git output is sanitized so a token can never reach a log.
"""

import asyncio
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


async def clone_repository(clone_url: str, branch: str, workspace_path: Path) -> str:
    """Clone ``clone_url`` at ``branch`` into ``workspace_path``; return the pinned commit SHA."""
    clone = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        branch,
        clone_url,
        str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(
            clone.communicate(), timeout=float(settings.ACQUISITION_TIMEOUT_SECONDS)
        )
    except TimeoutError:
        clone.kill()
        await clone.wait()
        raise TimeoutError(
            f"Repository clone timed out after {settings.ACQUISITION_TIMEOUT_SECONDS} seconds."
        ) from None
    if clone.returncode != 0:
        raise RepositoryCloneError(
            "Git clone failed: " + sanitize_git_output(stderr.decode("utf-8", errors="replace"))
        )

    rev = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "HEAD",
        cwd=str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(
            rev.communicate(), timeout=float(settings.ACQUISITION_TIMEOUT_SECONDS)
        )
    except TimeoutError:
        rev.kill()
        await rev.wait()
        raise RepositoryCloneError("Timed out resolving the cloned commit SHA.") from None
    if rev.returncode != 0:
        raise RepositoryCloneError("Failed to resolve the cloned commit SHA.")
    return stdout.decode("utf-8").strip()
