"""Workspace lifecycle: run-scoped allocation, teardown, and the startup sweep.

Three defects motivated these tests, all of them reachable in production and none of them visible
in development, where one analysis runs at a time and nothing is ever killed mid-run:

1. the analysis workspace path was derived from the integration id, so two concurrent analyses of
   one integration shared a directory — the second `git clone` failed against a non-empty
   directory, and the first run's teardown deleted the tree underneath it;
2. the same derived path meant a run killed before its `finally` (a redeploy, an OOM) left a
   directory that blocked every later run of that integration, permanently;
3. `WORKSPACE_RETENTION_HOURS` was read by nothing, so those orphans were never reclaimed.
"""

import os
import time
import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.repository.workspace import WorkspaceManager

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
PROJECT = uuid.UUID("22222222-2222-2222-2222-222222222222")
SCOPE = uuid.UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(base_dir=str(tmp_path / "workspaces"))


def _age(path: Path, hours: float) -> None:
    """Backdate a path's mtime, so retention can be tested without waiting."""
    when = time.time() - hours * 3600
    os.utime(path, (when, when))


def _age_tree(path: Path, hours: float) -> None:
    """Backdate a whole tree, which is what an abandoned workspace actually looks like.

    Backdating only the directory would leave recent files inside it, and the sweeper deliberately
    keeps any directory holding recent content.
    """
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            _age(Path(root) / name, hours)
        for name in dirs:
            _age(Path(root) / name, hours)
    _age(path, hours)


# ============================================================
# 1. A run owns its workspace
# ============================================================


def test_concurrent_runs_of_one_scope_get_different_directories(
    manager: WorkspaceManager,
) -> None:
    first, first_ref = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    second, second_ref = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)

    assert first != second
    assert first.is_dir() and second.is_dir()
    # Neither is a prefix of the other: they are siblings, not the same tree.
    assert not first.is_relative_to(second) and not second.is_relative_to(first)
    assert first_ref != second_ref


def test_one_runs_teardown_leaves_the_other_run_intact(manager: WorkspaceManager) -> None:
    """The failure that mattered: request B's `finally` deleted request A's clone."""
    first, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    second, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    (first / "clone.txt").write_text("first", encoding="utf-8")
    (second / "clone.txt").write_text("second", encoding="utf-8")

    assert manager.cleanup_workspace(second) is True

    assert not second.exists()
    assert first.is_dir()
    assert (first / "clone.txt").read_text(encoding="utf-8") == "first"


def test_an_orphan_does_not_block_a_new_run(manager: WorkspaceManager) -> None:
    """A directory left by a killed run must not stop the next one.

    The old derived path meant this was permanent: every later analysis of that integration failed
    at the clone step, with an error naming the repository rather than the workspace.
    """
    orphan, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    (orphan / "half-a-clone.txt").write_text("killed mid-clone", encoding="utf-8")

    fresh, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)

    assert fresh != orphan
    assert fresh.is_dir()
    assert orphan.is_dir()  # still there — reclaiming it is the sweeper's job, not this one's


def test_teardown_prunes_the_tenant_directories_it_emptied(manager: WorkspaceManager) -> None:
    workspace, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    assert workspace.is_dir()

    manager.cleanup_workspace(workspace)

    assert not workspace.exists()
    # The empty org/project/scope chain is gone too; the base directory is not.
    assert not (manager.base_dir / str(ORG)).exists()
    assert manager.base_dir.exists()


def test_teardown_keeps_a_tenant_directory_that_still_holds_a_run(
    manager: WorkspaceManager,
) -> None:
    first, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    second, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)

    manager.cleanup_workspace(first)

    assert second.is_dir()
    assert second.parent.is_dir()


def test_the_snapshot_flow_keeps_its_derived_path(manager: WorkspaceManager) -> None:
    """`inspection` and `discovery` recompute this path; it must stay deterministic."""
    first, first_ref = manager.allocate_workspace(ORG, PROJECT, SCOPE)
    second, second_ref = manager.allocate_workspace(ORG, PROJECT, SCOPE)

    assert first == second
    assert first_ref == second_ref
    assert first == manager.get_workspace_path(ORG, PROJECT, SCOPE)


# ============================================================
# 2. The startup sweep
# ============================================================


def test_sweep_removes_a_workspace_past_retention(
    manager: WorkspaceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WORKSPACE_RETENTION_HOURS", 24)
    orphan, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    (orphan / "clone.txt").write_text("abandoned", encoding="utf-8")
    _age_tree(orphan, 25)

    assert manager.sweep_expired() == 1
    assert not orphan.exists()


def test_sweep_keeps_a_workspace_inside_retention(
    manager: WorkspaceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WORKSPACE_RETENTION_HOURS", 24)
    live, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    _age(live, 1)

    assert manager.sweep_expired() == 0
    assert live.is_dir()


def test_sweep_keeps_an_old_directory_that_holds_a_recent_run(
    manager: WorkspaceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An in-flight run must survive even if its parent looks stale."""
    monkeypatch.setattr(settings, "WORKSPACE_RETENTION_HOURS", 24)
    old_orphan, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    live, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    # Backdate everything except the live run's own leaf.
    _age_tree(old_orphan, 30)
    _age(live.parent, 30)
    _age(manager.base_dir / str(ORG), 30)

    manager.sweep_expired()

    assert live.is_dir(), "the in-flight run was swept"
    assert not old_orphan.exists(), "the expired sibling was not reclaimed"


def test_sweep_removes_the_emptied_tenant_chain(
    manager: WorkspaceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WORKSPACE_RETENTION_HOURS", 24)
    orphan, _ = manager.allocate_run_workspace(ORG, PROJECT, SCOPE)
    _age_tree(orphan, 48)

    manager.sweep_expired()

    assert not (manager.base_dir / str(ORG)).exists()
    assert manager.base_dir.exists()


def test_sweep_never_removes_the_base_directory(
    manager: WorkspaceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WORKSPACE_RETENTION_HOURS", 0)
    manager.base_dir.mkdir(parents=True, exist_ok=True)
    _age(manager.base_dir, 100)

    assert manager.sweep_expired() == 0
    assert manager.base_dir.is_dir()


def test_sweep_on_a_missing_base_directory_is_a_no_op(
    manager: WorkspaceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WORKSPACE_RETENTION_HOURS", 24)
    assert manager.sweep_expired() == 0
