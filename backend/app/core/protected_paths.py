"""Paths Fussion must never write, whatever a plan or a user says (FR-096, CLAUDE.md §4.9).

This is an absolute rule, not a policy an approved plan can override: `widget_target_path` is
typed by hand today, so `.github/workflows/deploy.yml` is a plausible mistake as well as a
plausible attack, and the PR would prepend a JavaScript import to a workflow file.

Deliberately conservative in the other direction too: the patterns match infrastructure,
credentials, auth, payment and schema files, and must not match an ordinary application shell
(`app/layout.tsx`, `src/app/layout.tsx`, `index.html`) or Fussion's own generated components.
"""

import re

# Every pattern is case-insensitive. A mixed table was worse than either choice consistently:
# `Secrets/`, `Credentials/`, `Auth/`, `Payments/` and `Migrations/` are all real directory
# spellings, and each returned "not protected" while `Dockerfile` and `Stripe` were caught.
_RAW_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(^|/)\.env($|\.|/)", "environment file"),
    (r"(^|/)\.envrc$", "environment file"),
    (r"(^|/)\.npmrc$", "package registry credentials"),
    (r"(^|/)credentials?(/|$)", "credentials directory"),
    (r"(^|/)secrets?(/|$)", "secrets directory"),
    (r"(^|/)\.github/(workflows|actions)/", "CI workflow"),
    (r"(^|/)\.gitlab-ci\.ya?ml$", "CI workflow"),
    (r"(^|/)\.circleci(/|$)", "CI workflow"),
    (r"(^|/)(jenkinsfile|azure-pipelines\.ya?ml|bitbucket-pipelines\.ya?ml)$", "CI workflow"),
    (r"(^|/)infrastructure(/|$)", "infrastructure directory"),
    (r"(^|/)(docker-compose[^/]*\.ya?ml|dockerfile[^/]*)$", "container build"),
    (r"(^|/)(fly\.toml|vercel\.json|netlify\.toml|render\.ya?ml|app\.ya?ml)$", "deployment configuration"),
    (r"(^|/)(k8s|kubernetes|helm|charts|terraform)(/|$)", "deployment configuration"),
    (r"\.(tf|tfvars)$", "infrastructure as code"),
    (r"(^|/)(auth|authentication|authorization)(/|\.[a-z]+$)", "authentication code"),
    (r"(^|/)[^/]*(nextauth|clerk|auth0)[^/]*", "authentication code"),
    # Next.js middleware is the canonical authentication enforcement point, and a client
    # component imported into the edge runtime fails on every request.
    (r"(^|/)middleware\.[a-z]+$", "request middleware (authentication enforcement)"),
    (r"(^|/)(payment|payments|billing|checkout)(/|\.[a-z]+$)", "payment code"),
    (r"(^|/)[^/]*stripe[^/]*", "payment code"),
    (r"(^|/)(migrations|migration|alembic)(/|$)", "database migrations"),
    (r"\.(sql|prisma)$", "database schema"),
    (r"(^|/)schema\.[a-z]+$", "database schema"),
)

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in _RAW_PATTERNS
)


def protected_reason(path: str) -> str | None:
    """Return why `path` is protected, or None if Fussion may write it.

    Matching is case-insensitive throughout, on the POSIX-normalised path, ignoring a leading
    `./` or `/`.
    """
    candidate = path.replace("\\", "/").strip()
    while candidate.startswith(("./", "/")):
        candidate = candidate.lstrip("/").removeprefix("./")
    for pattern, reason in _PATTERNS:
        if pattern.search(candidate):
            return reason
    return None
