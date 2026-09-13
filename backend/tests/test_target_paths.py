"""Step C · C11 — the widget target path gate.

One gate for a typed path and an analyst-chosen one: a path reaches the integration only if it is
repository-relative, traversal-free, control-character-free, within the column's length, and not
protected.
"""

import pytest

from app.core.target_paths import MAX_WIDGET_TARGET_LENGTH, unsafe_target_reason


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/layout.tsx", None),
        ("src/app/layout.tsx", None),
        ("index.html", None),
        ("pages/_app.tsx", None),
        ("", "empty path"),
        ("   ", "empty path"),
        ("/etc/passwd", "absolute path"),
        ("\\etc\\passwd", "absolute path"),
        ("C:/Windows/System32", "absolute path"),
        ("app\\layout.tsx", "backslash in path"),
        ("a/../b", "path is not normalised"),
        ("app//layout.tsx", "path is not normalised"),
        ("../b", "path traversal"),
        ("a/../../b", "path is not normalised"),
        ("index.html\x00", "contains control characters"),
        ("a\nb", "contains control characters"),
        (".github/workflows/deploy.yml", "protected path: CI workflow"),
        (".env", "protected path: environment file"),
    ],
)
def test_unsafe_target_reason(path: str, expected: str | None) -> None:
    assert unsafe_target_reason(path) == expected


def test_a_path_longer_than_the_column_is_refused() -> None:
    # The column is String(255); longer is a Postgres DataError, invisible on SQLite (CLAUDE.md §9.1).
    over_long = "a" * (MAX_WIDGET_TARGET_LENGTH + 1)
    assert unsafe_target_reason(over_long) == f"longer than {MAX_WIDGET_TARGET_LENGTH} characters"
    assert unsafe_target_reason("a" * MAX_WIDGET_TARGET_LENGTH) is None
