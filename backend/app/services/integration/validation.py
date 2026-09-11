import re

from app.models.website_integration import WebsiteFramework
from app.schemas.website_integration import IntegrationPlanPayload

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


class StaticValidationError(Exception):
    def __init__(self, issues: list[str]) -> None:
        super().__init__(f"Static validation failed with {len(issues)} issue(s): {'; '.join(issues)}")
        self.issues = issues


class StaticValidator:
    """
    Performs deterministic static analysis on generated integration artifacts.
    Guarantees security containment, marker presence, and absence of credentials.
    """

    @staticmethod
    def validate(
        framework: WebsiteFramework,
        plan: IntegrationPlanPayload,
        files: dict[str, str],
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

        if issues:
            raise StaticValidationError(issues)

        return issues
