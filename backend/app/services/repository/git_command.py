"""Run git off the event loop, identically on every platform and every loop.

`asyncio.create_subprocess_exec` is not usable here. The development server installs Windows'
SelectorEventLoop — psycopg's async driver cannot use Proactor (`run_dev.py`, CLAUDE.md §8) — and
that loop has no subprocess transport on Windows, so the call raises `NotImplementedError`. It turned
every analysis into an unhandled 500, and the same call in `acquisition` would have failed the same
way the first time anyone took a snapshot on a developer's machine.

A blocking `subprocess.run` in a worker thread behaves identically under every loop and on every
platform, so there is one implementation rather than one per call site — and the development server
and production exercise the same code.
"""

import asyncio
import subprocess
from collections.abc import Sequence
from pathlib import Path


async def run_git(
    args: Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout_seconds: float,
    timeout_message: str,
) -> subprocess.CompletedProcess[bytes]:
    """Run ``git`` with a structured argument list, off the event loop.

    ``shell`` is never used: every call passes an argument list, so a branch name or a repository
    path can never become part of a command.

    A timeout is raised as the builtin ``TimeoutError`` — not ``subprocess.TimeoutExpired`` — so
    callers map one exception to one outcome, and an HTTP layer can answer it with a single status.
    """

    def _invoke() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )

    try:
        return await asyncio.to_thread(_invoke)
    except subprocess.TimeoutExpired:
        raise TimeoutError(timeout_message) from None
