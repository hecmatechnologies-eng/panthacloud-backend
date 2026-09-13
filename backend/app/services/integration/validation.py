import re

from app.core.protected_paths import protected_reason
from app.models.website_integration import (
    DEFAULT_FRAMEWORK_SKILL_ID,
    GENERIC_HTML_SKILL_ID,
)
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.artifacts import (
    HTML_BEGIN,
    HTML_END,
    HTML_SUFFIXES,
    MANAGED_BLOCKS,
    REACT_BEGIN_IMPORT,
    REACT_END_JSX,
    REACT_SUFFIXES,
    MarkerPair,
    marker_pairs_for_path,
)
from app.services.integration.code_scan import scan_generated_code

SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
]

FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"(?i)[a-z]:[\\/](windows|users|program\s*files)"),
    re.compile(r"/(etc|var|usr|bin|sbin|root)/"),
    re.compile(r"\\\\\w+\\\w+"),  # UNC share
]

# A file is compared against *its own* marker family only: treating any marker pair as a managed
# block, wherever it appeared, is what let an edit wrapped in marker text bypass the comparison
# entirely (CLAUDE.md §3). The families and the suffix map live with the patchers that emit them,
# in artifacts.py, so the two cannot drift apart — imported under its own name, not aliased.


def _block_pattern(pair: MarkerPair) -> re.Pattern[str]:
    return re.compile(re.escape(pair[0]) + r".*?" + re.escape(pair[1]), re.DOTALL)


def managed_block_contents(content: str, pairs: tuple[MarkerPair, ...]) -> list[str]:
    """The text inside each managed block — what Fussion is responsible for."""
    found: list[str] = []
    for pair in pairs:
        for match in _block_pattern(pair).finditer(content):
            found.append(match.group(0))
    return found


def marker_discipline_issues(path: str, content: str) -> list[str]:
    """Markers must be exactly the family this file allows, once each, alone on their lines.

    Without this, marker text is a skeleton key: the comparison below ignores whatever sits
    between a BEGIN and an END, so an attacker-supplied or agent-generated edit wrapped in
    markers is invisible, and a customer region that merely looks like a managed block can be
    replaced by the patcher.
    """
    issues: list[str] = []
    allowed = marker_pairs_for_path(path)
    allowed_markers = {marker for pair in allowed for marker in pair}

    for pair in MANAGED_BLOCKS:
        for marker in pair:
            occurrences = content.count(marker)
            if marker not in allowed_markers:
                if occurrences:
                    issues.append(
                        f"'{path}' contains a Fussion marker from another framework family "
                        f"({occurrences} occurrence(s))."
                    )
                continue
            if occurrences > 1:
                issues.append(f"'{path}' repeats a Fussion marker {occurrences} times; one is allowed.")

    for line_number, line in enumerate(content.splitlines(), start=1):
        for marker in allowed_markers:
            if marker in line and line.strip() != marker:
                issues.append(
                    f"'{path}' has a Fussion marker sharing line {line_number} with other content; "
                    "a marker must stand alone on its line."
                )
    return issues


def _customer_segments(content: str, pairs: tuple[MarkerPair, ...]) -> list[tuple[int, str]]:
    """(offset, text) for each stretch of content outside Fussion-managed blocks."""
    spans = sorted(match.span() for pair in pairs for match in _block_pattern(pair).finditer(content))
    segments: list[tuple[int, str]] = []
    cursor = 0
    for start, end in spans:
        if start >= cursor:
            segments.append((cursor, content[cursor:start]))
            cursor = end
    segments.append((cursor, content[cursor:]))
    return segments


def _customer_chars(content: str, pairs: tuple[MarkerPair, ...]) -> list[tuple[str, int]]:
    """Non-whitespace characters outside Fussion-managed blocks, each with its line number."""
    chars: list[tuple[str, int]] = []
    for offset, text in _customer_segments(content, pairs):
        line = content.count("\n", 0, offset) + 1
        for char in text:
            if char == "\n":
                line += 1
            elif not char.isspace():
                chars.append((char, line))
    return chars


def first_changed_line(original: str, generated: str, pairs: tuple[MarkerPair, ...]) -> int | None:
    """
    Return the original line number where customer content (everything outside this file's own
    Fussion-managed blocks) first differs between `original` and `generated`, or None if it
    is identical. Whitespace is ignored, so line endings, indentation and the line breaks the
    patchers add around managed blocks do not count; any other insertion, deletion or
    rewrite does. Known limit: a whitespace-only change is not detected.
    """
    before = _customer_chars(original, pairs)
    after = _customer_chars(generated, pairs)
    for (old, line), (new, _) in zip(before, after, strict=False):
        if old != new:
            return line
    if len(before) > len(after):
        return before[len(after)][1]
    if len(after) > len(before):
        return before[-1][1] if before else 1
    return None


class StaticValidationError(Exception):
    def __init__(self, issues: list[str]) -> None:
        super().__init__(f"Static validation failed with {len(issues)} issue(s): {'; '.join(issues)}")
        self.issues = issues


class StaticValidator:
    """
    Performs deterministic static analysis on generated integration artifacts.
    Guarantees security containment, marker presence, absence of credentials, and that
    modified files preserve their original content.
    """

    @staticmethod
    def validate(
        framework_skill_id: str,
        plan: IntegrationPlanPayload,
        files: dict[str, str],
        original_files: dict[str, str],
    ) -> list[str]:
        issues: list[str] = []

        allowed_files = set(plan.files_to_create + plan.files_to_modify)
        actual_files = set(files.keys())

        # 1. Reject unexpected or unallowed file modifications
        unexpected = actual_files - allowed_files
        if unexpected:
            issues.append(f"Forbidden files generated outside declared plan: {', '.join(sorted(unexpected))}")

        # Missing planned files
        missing = allowed_files - actual_files
        if missing:
            issues.append(f"Declared files missing from generation: {', '.join(sorted(missing))}")

        # 1b. Protected paths are absolute (FR-096, CLAUDE.md §4.9). Checked against everything
        # declared as well as everything generated, so a protected path cannot arrive by either
        # route — and never mind that a plan "approved" it.
        for path in sorted(actual_files | allowed_files):
            reason = protected_reason(path)
            if reason:
                issues.append(f"'{path}' is a protected path ({reason}) and must never be written.")

        # 2. Content validations
        for path, content in files.items():
            # Check secrets
            for pat in SECRET_PATTERNS:
                if pat.search(content):
                    issues.append(f"Potential secret or credential pattern detected in '{path}'.")
                    break

            # Check absolute system paths
            for pat in FORBIDDEN_PATH_PATTERNS:
                if pat.search(content):
                    issues.append(f"Absolute or system path pattern detected in '{path}'.")
                    break

            # Framework specific marker verification
            # Marker constants come from artifacts.py rather than being spelled again here:
            # re-typing them is how a marker change breaks the validator silently.
            if framework_skill_id == DEFAULT_FRAMEWORK_SKILL_ID:
                if (
                    path.lower().endswith(REACT_SUFFIXES)
                    and path in plan.files_to_modify
                    and (REACT_BEGIN_IMPORT not in content or REACT_END_JSX not in content)
                ):
                    issues.append(f"Managed integration markers missing from modified React layout '{path}'.")
                if "lib/fussion-assistant.ts" in path:
                    for key in ("projectId", "assistantId", "brandColor", "position"):
                        if f'"{key}"' not in content and f"{key}:" not in content:
                            issues.append(f"Required configuration key '{key}' missing from '{path}'.")

            elif (
                framework_skill_id == GENERIC_HTML_SKILL_ID
                and path.lower().endswith(HTML_SUFFIXES)
                and path in plan.files_to_modify
                and (HTML_BEGIN not in content or HTML_END not in content)
            ):
                issues.append(f"Managed integration markers missing from modified HTML file '{path}'.")

        # 2b. Generated code is scanned (FR-097): created files entirely, and for a modified file
        # only the content of its managed blocks. A customer's own code is theirs, and may
        # legitimately do everything the scan rejects.
        for path in sorted(plan.files_to_create):
            if path in files:
                issues.extend(scan_generated_code(path, files[path]))
        for path in sorted(plan.files_to_modify):
            if path not in files:
                continue
            for block in managed_block_contents(files[path], marker_pairs_for_path(path)):
                issues.extend(scan_generated_code(path, block))

        # 3. Modified files may change only Fussion-managed blocks (CLAUDE.md §4.8), and marker
        # discipline is what makes that comparison meaningful.
        # Report line numbers only: quoting customer source would copy it into audit logs.
        for path in plan.files_to_modify:
            if path not in files:
                continue  # already reported as missing
            if path not in original_files:
                issues.append(
                    f"'{path}' is planned as a modification but its original content was not read."
                )
                continue

            marker_issues = marker_discipline_issues(path, files[path])
            issues.extend(marker_issues)
            if marker_issues:
                # With the markers in doubt, the comparison below cannot be trusted: it ignores
                # whatever sits inside a block it believes Fussion owns.
                continue

            line = first_changed_line(original_files[path], files[path], marker_pairs_for_path(path))
            if line is not None:
                issues.append(
                    f"'{path}' changes existing content outside Fussion-managed blocks at "
                    f"original line {line}."
                )

        if issues:
            raise StaticValidationError(issues)

        return issues
