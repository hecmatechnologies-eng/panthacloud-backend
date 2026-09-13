"""What a widget target path may be (FR-096, step C11).

`widget_target_path` is written into a customer's repository. After C11 it is chosen by the analyst
rather than typed by a user, so it is model output and untrusted (`CLAUDE.md` §4.5). The checks
here are the ones the configuration schema and the analyst's target selection both apply, so a path
reaches the integration only if it passed the same gate however it was chosen.
"""

import posixpath

from app.core.protected_paths import protected_reason

# The column is String(255); a longer path would be a Postgres DataError, invisible on SQLite
# (`CLAUDE.md` §9.1).
MAX_WIDGET_TARGET_LENGTH = 255

_FORBIDDEN_PARTS = {"", ".", ".."}


def unsafe_target_reason(path: str) -> str | None:
    """Return why `path` cannot be a widget target, or None if it may be.

    Rejects an absolute path, a path that is not normalised, traversal, control characters and an
    over-long path, then defers to the protected-path rule. The path is not required to exist:
    whether the file is present is checked against the repository at run time.
    """
    candidate = path.strip()
    if not candidate:
        return "empty path"
    if len(candidate) > MAX_WIDGET_TARGET_LENGTH:
        return f"longer than {MAX_WIDGET_TARGET_LENGTH} characters"
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in candidate):
        return "contains control characters"
    if candidate.startswith(("/", "\\")):
        return "absolute path"
    if len(candidate) > 1 and candidate[1] == ":":
        return "absolute path"
    if "\\" in candidate:
        return "backslash in path"

    normalised = candidate
    if normalised != posixpath.normpath(normalised):
        return "path is not normalised"
    if any(part in _FORBIDDEN_PARTS for part in normalised.split("/")):
        return "path traversal"

    reason = protected_reason(normalised)
    if reason:
        return f"protected path: {reason}"
    return None
