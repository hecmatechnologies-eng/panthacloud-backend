"""Directories that are never project source, for every reader of a customer repository.

One source of truth. `repository/reader.py` (the analyst's read_tree / read_file / search_code),
`repository/discovery.py` (the deterministic inventory) and `analysis/pre_analysis.py` each kept
their own copy of this list and the copies drifted:

- `vendor/` and `.output/` were skipped by pre-analysis but listable and searchable by the
  analyst's tools, so a vendored tree could consume the run's tool-call budget on code the
  deterministic pass had already decided was not the customer's;
- `.ruff_cache/` was hidden from discovery but visible to the reader;
- `out/`, `coverage/`, `.turbo/` and `.cache/` were hidden from the reader and pre-analysis but
  still inventoried by discovery.

Judgement is per path component and normalised (see `reader._normalize_part`): Windows folds
`.GIT` and `.git.` onto `.git`, so a case- or trailing-dot variant must not smuggle a path past
the list.

Deleting this folder and its three importers' references removes the capability — the list is
data, with no behaviour attached (CLAUDE.md §9.1).
"""

from typing import Final

# VCS metadata, package dependencies, build output, tool caches and vendored trees.
IGNORED_DIRS: Final[frozenset[str]] = frozenset(
    {
        # VCS metadata — also carries the clone's access token in .git/config.
        ".git",
        # Package dependencies.
        "node_modules",
        "vendor",
        ".venv",
        "venv",
        "__pycache__",
        # Build output.
        ".next",
        ".output",
        ".turbo",
        "dist",
        "build",
        "out",
        "coverage",
        # Tool caches.
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)
