import re

from app.models.website_integration import WebsiteFramework
from app.schemas.website_integration import IntegrationPlanPayload
from app.services.integration.artifacts import MANAGED_BLOCKS

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

MANAGED_BLOCK_PATTERNS = [
    re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    for begin, end in MANAGED_BLOCKS
]


def _customer_segments(content: str) -> list[tuple[int, str]]:
    """(offset, text) for each stretch of content outside Fussion-managed blocks."""
    spans = sorted(match.span() for pat in MANAGED_BLOCK_PATTERNS for match in pat.finditer(content))
    segments: list[tuple[int, str]] = []
    cursor = 0
    for start, end in spans:
        if start >= cursor:
            segments.append((cursor, content[cursor:start]))
            cursor = end
    segments.append((cursor, content[cursor:]))
    return segments


def _customer_chars(content: str) -> list[tuple[str, int]]:
    """Non-whitespace characters outside Fussion-managed blocks, each with its line number."""
    chars: list[tuple[str, int]] = []
    for offset, text in _customer_segments(content):
        line = content.count("\n", 0, offset) + 1
        for char in text:
            if char == "\n":
                line += 1
            elif not char.isspace():
                chars.append((char, line))
    return chars


def first_changed_line(original: str, generated: str) -> int | None:
    """
    Return the original line number where customer content (everything outside
    Fussion-managed blocks) first differs between `original` and `generated`, or None if it
    is identical. Whitespace is ignored, so line endings, indentation and the line breaks the
    patchers add around managed blocks do not count; any other insertion, deletion or
    rewrite does. Known limit: a whitespace-only change is not detected.
    """
    before = _customer_chars(original)
    after = _customer_chars(generated)
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
        framework: WebsiteFramework,
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
            if framework == WebsiteFramework.REACT_NEXTJS:
                if (
                    path.endswith((".tsx", ".jsx", ".ts", ".js"))
                    and path in plan.files_to_modify
                    and ("FUSSION-ASSISTANT:BEGIN" not in content or "FUSSION-ASSISTANT:END" not in content)
                ):
                    issues.append(f"Managed integration markers missing from modified React layout '{path}'.")
                if "lib/fussion-assistant.ts" in path:
                    for key in ("projectId", "assistantId", "brandColor", "position"):
                        if f'"{key}"' not in content and f"{key}:" not in content:
                            issues.append(f"Required configuration key '{key}' missing from '{path}'.")

            elif (
                framework == WebsiteFramework.GENERIC_HTML
                and path.endswith(".html")
                and path in plan.files_to_modify
                and ("<!-- FUSSION-ASSISTANT:BEGIN -->" not in content or "<!-- FUSSION-ASSISTANT:END -->" not in content)
            ):
                issues.append(f"Managed integration markers missing from modified HTML file '{path}'.")

        # 3. Modified files may change only Fussion-managed blocks (CLAUDE.md §4.8).
        # Report line numbers only: quoting customer source would copy it into audit logs.
        for path in plan.files_to_modify:
            if path not in files:
                continue  # already reported as missing
            if path not in original_files:
                issues.append(
                    f"'{path}' is planned as a modification but its original content was not read."
                )
                continue
            line = first_changed_line(original_files[path], files[path])
            if line is not None:
                issues.append(
                    f"'{path}' changes existing content outside Fussion-managed blocks at "
                    f"original line {line}."
                )

        if issues:
            raise StaticValidationError(issues)

        return issues
