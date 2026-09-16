"""The real clone path, under the event loop the development server installs.

The C10 tests stub `clone_repository`, so the git invocation itself was never exercised — which is
how it shipped calling `asyncio.create_subprocess_exec` while `run_dev.py` forces Windows'
SelectorEventLoop, where that call raises `NotImplementedError` and every analysis became a 500.

These tests drive the coroutine on an explicit selector loop, so the regression cannot come back
unseen. They clone a local `file://` repository: no network, no credentials, no paid API.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.analysis.clone import RepositoryCloneError, clone_repository


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout.strip()


def _origin_repository(tmp_path: Path) -> tuple[str, str, str]:
    """A committed local repository. Returns its `file://` URL, its HEAD SHA and its branch."""
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "package.json").write_text(
        '{"dependencies": {"next": "14.0.0"}}', encoding="utf-8"
    )
    (origin / "app").mkdir()
    (origin / "app" / "layout.tsx").write_text("export default null;", encoding="utf-8")
    _git(["init"], origin)
    _git(["config", "user.email", "dev@acme.dev"], origin)
    _git(["config", "user.name", "Dev"], origin)
    _git(["add", "."], origin)
    _git(["commit", "-m", "init"], origin)
    head = _git(["rev-parse", "HEAD"], origin)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], origin)
    return origin.as_uri(), head, branch


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()


def test_clone_and_rev_parse_run_on_the_selector_loop(tmp_path: Path) -> None:
    url, head, branch = _origin_repository(tmp_path)
    destination = tmp_path / "clone"

    loop = _selector_loop()
    try:
        sha = loop.run_until_complete(clone_repository(url, branch, destination))
    finally:
        loop.close()

    assert sha == head
    assert (destination / "package.json").is_file()
    assert (destination / "app" / "layout.tsx").is_file()


def test_unreadable_repository_raises_a_clone_error(tmp_path: Path) -> None:
    loop = _selector_loop()
    try:
        with pytest.raises(RepositoryCloneError):
            loop.run_until_complete(
                clone_repository((tmp_path / "absent").as_uri(), "main", tmp_path / "clone")
            )
    finally:
        loop.close()
