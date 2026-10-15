"""One canonical ignore list for every reader of a customer repository (CLAUDE.md §7, §9.1).

`repository/reader.py`, `repository/discovery.py` and `analysis/pre_analysis.py` each kept their
own copy of "directories that are not project source", and the copies drifted. The drift is not
cosmetic: pre-analysis skipped `vendor/` while the analyst's `read_tree` and `search_code` could
still list and search it, so a vendored tree could consume the run's tool-call budget on code the
deterministic pass had already decided was not the customer's.
"""

from app.services.analysis import pre_analysis
from app.services.repository import discovery, reader


def test_every_repository_reader_ignores_the_same_directories() -> None:
    assert set(reader._IGNORED_DIRS) == set(discovery.IGNORE_DIR_NAMES)
    assert set(reader._IGNORED_DIRS) == set(pre_analysis._IGNORED_DIRS)


def test_the_analyst_cannot_read_trees_pre_analysis_already_ignores() -> None:
    # These are skipped by the deterministic pass but were listable and searchable by the
    # analyst's read tools, so a vendored or tool-cache tree could eat the run's budget.
    for name in ("vendor", ".output", ".ruff_cache"):
        assert name in reader._IGNORED_DIRS, name


def test_one_module_owns_the_policy() -> None:
    # Local import: if the module is missing this fails as one test, not as a collection error.
    from app.core import read_policy

    assert reader._IGNORED_DIRS is read_policy.IGNORED_DIRS
    assert discovery.IGNORE_DIR_NAMES is read_policy.IGNORED_DIRS
    assert pre_analysis._IGNORED_DIRS is read_policy.IGNORED_DIRS


def test_the_policy_covers_vcs_dependencies_and_build_output() -> None:
    from app.core import read_policy

    expected = {
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
    }
    assert expected <= set(read_policy.IGNORED_DIRS)
