"""Golden evaluation corpus (FR-084).

Small repositories, in code rather than as fixture trees, covering both supported frameworks, a
layout variant, an unconventional shell, and one case that must be refused. Half the corpus tests
judgment, not capability: an analyst that guesses on an unrecognisable repository is worse than one
that declines.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvalCase:
    name: str
    files: dict[str, str]
    expect_skill_id: str | None = None
    expect_candidate: str | None = None
    should_refuse: bool = False


_NEXT_PACKAGE = '{"dependencies": {"next": "14.0.0", "react": "18.2.0"}}'
_LAYOUT = "export default function Root({ children }) { return children; }"

CORPUS: tuple[EvalCase, ...] = (
    EvalCase(
        name="nextjs-app-router",
        files={"package.json": _NEXT_PACKAGE, "app/layout.tsx": _LAYOUT},
        expect_skill_id="nextjs-app-router",
        expect_candidate="app/layout.tsx",
    ),
    EvalCase(
        name="nextjs-src-layout",
        files={"package.json": _NEXT_PACKAGE, "src/app/layout.tsx": _LAYOUT},
        expect_skill_id="nextjs-app-router",
        expect_candidate="src/app/layout.tsx",
    ),
    EvalCase(
        name="static-html",
        files={"index.html": "<html><body><h1>Store</h1></body></html>"},
        expect_skill_id="generic-html",
        expect_candidate="index.html",
    ),
    EvalCase(
        name="unconventional-shell",
        files={"package.json": _NEXT_PACKAGE, "src/shell/Root.tsx": _LAYOUT},
        should_refuse=True,
    ),
    EvalCase(
        name="no-frontend",
        files={"manage.py": "print('django')", "README.md": "# A backend service"},
        should_refuse=True,
    ),
)
