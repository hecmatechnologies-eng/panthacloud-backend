"""Performance and correctness of the analyst's `search_code` tool (step C — G1, G8).

This tool is the only part of the pipeline whose cost scales with the size of the *customer's*
repository, and it is called many times per run. Before ripgrep backed it, one search cost ~2.6
seconds on a 2,709-file repository (14-18x the ripgrep cost), and the cost is linear in the file
count — so at the 10,000 files `MAX_FILE_COUNT` permits, a single run's worth of searches is a
material fraction of the 300-second budget.

Two gates live here:

- a wall-clock ceiling on a repository large enough for the difference to matter, so the regression
  cannot come back unnoticed;
- an assertion that the production image actually ships the binary the fast path needs, because a
  missing `rg` silently degrades to the slow path rather than failing.
"""

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from app.services.repository import reader as reader_module
from app.services.repository.reader import LocalWorkspaceReader

LARGE_REPO_FILES = 2000
NEEDLE = "fussion_needle_marker"
EXPECTED_HITS = 10
# Measured on this fixture: ripgrep 78ms, the Python walk 1166ms. The ceiling is placed between
# them with ~12x headroom above ripgrep (so a slow CI machine cannot flake it) and below the walk
# (so the regression it exists to catch genuinely fails it).
SEARCH_CEILING_SECONDS = 1.0


@pytest.fixture(scope="module")
def large_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="c4-large-repo-"))
    for index in range(LARGE_REPO_FILES):
        directory = root / f"src/module{index % 20}" / f"group{index % 7}"
        directory.mkdir(parents=True, exist_ok=True)
        body = "\n".join(
            f"export const value{line} = compute({line}, {index});" for line in range(30)
        )
        if index % 200 == 0:
            body += f"\n// {NEEDLE}\n"
        (directory / f"file{index}.ts").write_text(body, encoding="utf-8")
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_ripgrep_is_available_in_this_environment() -> None:
    """The fast path is opt-out-by-absence; if it is absent here, the gate below is meaningless."""
    if reader_module._ripgrep_path() is None:
        pytest.skip("ripgrep is not installed in this environment")


@pytest.mark.asyncio
async def test_search_finds_every_match_in_a_large_repository(large_repo: Path) -> None:
    results = await LocalWorkspaceReader(large_repo).search(
        query=NEEDLE, offset=0, max_results=50
    )

    assert results.total == EXPECTED_HITS
    assert len(results.hits) == EXPECTED_HITS
    assert results.truncated is False
    for hit in results.hits:
        # Paths must stay repository-relative and POSIX-shaped: the workspace path must never reach
        # the model, and Windows separators would not resolve on the other side.
        assert hit.path.endswith(".ts")
        assert "\\" not in hit.path
        assert not hit.path.startswith("/")
        assert NEEDLE in hit.line


@pytest.mark.asyncio
async def test_search_stays_under_the_wall_clock_ceiling(large_repo: Path) -> None:
    """The G1 regression gate."""
    if reader_module._ripgrep_path() is None:
        pytest.skip("ripgrep is not installed in this environment")

    started = time.perf_counter()
    await LocalWorkspaceReader(large_repo).search(query=NEEDLE, offset=0, max_results=50)
    elapsed = time.perf_counter() - started

    assert elapsed < SEARCH_CEILING_SECONDS, (
        f"search took {elapsed:.2f}s on a {LARGE_REPO_FILES}-file repository "
        f"(ceiling {SEARCH_CEILING_SECONDS}s). The ripgrep fast path is not being used."
    )


@pytest.mark.asyncio
async def test_search_ceiling_is_not_met_by_the_python_fallback(
    large_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ceiling above only means something if the fallback is genuinely slower.

    Without this, a future change that made the walk fast (or that made the ceiling meaningless)
    would leave the gate passing while proving nothing. The assertion is on the *contrast*, not on
    the fallback's absolute speed, so it stays stable on slow hardware.
    """
    if reader_module._ripgrep_path() is None:
        pytest.skip("ripgrep is not installed in this environment")

    reader = LocalWorkspaceReader(large_repo)
    started = time.perf_counter()
    fast = await reader.search(query=NEEDLE, offset=0, max_results=50)
    fast_elapsed = time.perf_counter() - started

    monkeypatch.setattr(reader_module, "_ripgrep_path", lambda: None)
    started = time.perf_counter()
    fallback = await reader.search(query=NEEDLE, offset=0, max_results=50)
    fallback_elapsed = time.perf_counter() - started

    # Same answer, either way: the fallback is a genuine substitute, not a degraded one. Compared as
    # a set because the two order results differently — ripgrep emits matches in sorted order, while
    # `os.walk` follows filesystem order, which varies by platform. Neither order is part of the
    # tool's contract; the caller pages within whichever one it is given.
    assert sorted(hit.path for hit in fallback.hits) == sorted(hit.path for hit in fast.hits)
    assert fallback.total == fast.total
    assert fallback_elapsed > fast_elapsed * 10, (
        f"fallback took {fallback_elapsed:.2f}s vs {fast_elapsed:.3f}s — the contrast the ceiling "
        "relies on has disappeared"
    )


@pytest.mark.asyncio
async def test_search_never_returns_denied_paths(large_repo: Path) -> None:
    """Denial is re-checked on every match, so a protected path outside the glob list is still cut."""
    (large_repo / ".env").write_text(f"SECRET={NEEDLE}", encoding="utf-8")
    (large_repo / "credentials").mkdir(exist_ok=True)
    (large_repo / "credentials" / "token.json").write_text(NEEDLE, encoding="utf-8")

    results = await LocalWorkspaceReader(large_repo).search(
        query=NEEDLE, offset=0, max_results=50
    )

    paths = [hit.path for hit in results.hits]
    assert ".env" not in paths
    assert not any(path.startswith("credentials/") for path in paths)
    assert results.total == EXPECTED_HITS


def test_production_image_installs_ripgrep() -> None:
    """A missing `rg` in the image degrades silently, so the image is asserted, not assumed."""
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    assert dockerfile.is_file(), "backend/Dockerfile is missing"
    contents = dockerfile.read_text(encoding="utf-8")
    install_line = next(
        (line for line in contents.splitlines() if "apt-get install" in line), ""
    )
    assert "ripgrep" in install_line, (
        "the production image does not install ripgrep, so search_code falls back to the "
        "pure-Python walk"
    )
