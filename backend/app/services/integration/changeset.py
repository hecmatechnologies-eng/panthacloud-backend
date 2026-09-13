"""Build the change set a run committed, so the Studio can show it without re-deriving (C12).

Re-deriving a diff from the *current* configuration and a stub layout is what showed the Studio a
file the pull request never contained (`CLAUDE.md` §3.1). The change set is computed once, at
generation time, from the exact bytes the run wrote, and served verbatim.
"""

import difflib
from typing import Any


def build_change_set(
    generated_files: dict[str, str],
    files_to_create: list[str],
    original_files: dict[str, str],
) -> list[dict[str, Any]]:
    """A per-file unified diff for everything the run wrote.

    Created files are diffed against empty; modified files against the content that was read. Paths
    are sorted so the stored set is deterministic.
    """
    create_set = set(files_to_create)
    changes: list[dict[str, Any]] = []
    for path in sorted(generated_files):
        content = generated_files[path]
        action = "create" if path in create_set else "modify"
        before = "" if action == "create" else original_files.get(path, "")
        changes.append({"path": path, "action": action, "diff": _unified_diff(before, content, path)})
    return changes


def _unified_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
