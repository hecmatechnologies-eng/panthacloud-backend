"""Golden evaluation corpus (FR-084).

Small repositories, in code rather than as fixture trees, covering both supported frameworks, a
layout variant, an unconventional shell, and one case that must be refused. Half the corpus tests
judgment, not capability: an analyst that guesses on an unrecognisable repository is worse than one
that declines.

Cases may also carry **budget ceilings** (``max_tokens``, ``max_tool_calls``). Those are inert
against the model-free analyzer CI runs, and live against ``harness_analyzer`` — so a real run that
costs more than it should fails the suite instead of merely being reported.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvalCase:
    name: str
    files: dict[str, str]
    expect_skill_id: str | None = None
    expect_candidate: str | None = None
    should_refuse: bool = False
    # Ceilings. None means "not asserted"; they are compared against what the analyzer reported.
    max_tokens: int | None = None
    max_tool_calls: int | None = None


_NEXT_PACKAGE = '{"dependencies": {"next": "14.0.0", "react": "18.2.0"}}'
_LAYOUT = "export default function Root({ children }) { return children; }"


def _large_tree(file_count: int = 400) -> dict[str, str]:
    """A repository with enough files that a per-call filesystem scan is expensive.

    The analyst reads a handful of files but searches many times; this is the shape in which a
    quadratic search tool becomes the run's dominant cost.
    """
    files: dict[str, str] = {
        "package.json": _NEXT_PACKAGE,
        "app/layout.tsx": _LAYOUT,
    }
    for index in range(file_count):
        files[f"app/components/Widget{index}.tsx"] = (
            f"export function Widget{index}() {{\n  return <div>widget {index}</div>;\n}}\n"
        )
    return files


CORPUS: tuple[EvalCase, ...] = (
    EvalCase(
        name="nextjs-app-router",
        files={"package.json": _NEXT_PACKAGE, "app/layout.tsx": _LAYOUT},
        expect_skill_id="nextjs-app-router",
        expect_candidate="app/layout.tsx",
        max_tokens=120_000,
        max_tool_calls=25,
    ),
    EvalCase(
        name="nextjs-src-layout",
        files={"package.json": _NEXT_PACKAGE, "src/app/layout.tsx": _LAYOUT},
        expect_skill_id="nextjs-app-router",
        expect_candidate="src/app/layout.tsx",
        max_tokens=120_000,
        max_tool_calls=25,
    ),
    EvalCase(
        name="static-html",
        files={"index.html": "<html><body><h1>Store</h1></body></html>"},
        expect_skill_id="generic-html",
        expect_candidate="index.html",
        max_tokens=80_000,
        max_tool_calls=15,
    ),
    EvalCase(
        name="unconventional-shell",
        files={"package.json": _NEXT_PACKAGE, "src/shell/Root.tsx": _LAYOUT},
        should_refuse=True,
        max_tokens=150_000,
        max_tool_calls=35,
    ),
    EvalCase(
        name="no-frontend",
        files={"manage.py": "print('django')", "README.md": "# A backend service"},
        should_refuse=True,
        max_tokens=60_000,
        max_tool_calls=12,
    ),
    # Frameworks no installed skill covers. The correct outcome today is a refusal, and these pin
    # that behaviour: when G2 adds a framework table, these become the cases it must satisfy.
    EvalCase(
        name="vite-react",
        files={
            "package.json": '{"dependencies": {"vite": "5.0.0", "react": "18.2.0"}}',
            "index.html": '<html><body><div id="root"></div></body></html>',
            "src/main.tsx": "createRoot(document.getElementById('root')!).render(<App />);",
        },
        should_refuse=True,
        max_tokens=200_000,
        max_tool_calls=45,
    ),
    EvalCase(
        name="remix",
        files={
            "package.json": '{"dependencies": {"@remix-run/react": "2.0.0", "react": "18.2.0"}}',
            "app/root.tsx": _LAYOUT,
        },
        should_refuse=True,
        max_tokens=200_000,
        max_tool_calls=45,
    ),
    EvalCase(
        name="astro",
        files={
            "package.json": '{"dependencies": {"astro": "4.0.0"}}',
            "src/pages/index.astro": "---\n---\n<html><body><h1>Site</h1></body></html>",
        },
        should_refuse=True,
        max_tokens=200_000,
        max_tool_calls=45,
    ),
    # The scaling case. The ceiling is what makes the analyst's search cost a failing test rather
    # than an observation.
    EvalCase(
        name="large-nextjs-tree",
        files=_large_tree(),
        expect_skill_id="nextjs-app-router",
        expect_candidate="app/layout.tsx",
        max_tokens=250_000,
        max_tool_calls=45,
    ),
)