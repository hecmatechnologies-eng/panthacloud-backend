"""Deterministic detection for the nextjs-app-router skill (FR-080).

Self-contained: prints a JSON object `{"match", "confidence", "reason"}` for a repository root.
"""

import json
import sys
from pathlib import Path

_LAYOUTS = (
    "app/layout.tsx",
    "app/layout.ts",
    "app/layout.jsx",
    "app/layout.js",
    "src/app/layout.tsx",
    "src/app/layout.ts",
    "src/app/layout.jsx",
    "src/app/layout.js",
)


def detect(repo_root: str | Path) -> dict:
    root = Path(repo_root)
    package = root / "package.json"
    if not package.is_file():
        return {"match": False, "confidence": 0.0, "reason": "no package.json"}

    try:
        data = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"match": False, "confidence": 0.0, "reason": f"unreadable package.json: {exc}"}

    dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "next" not in dependencies:
        return {"match": False, "confidence": 0.0, "reason": "next is not a dependency"}

    for layout in _LAYOUTS:
        if (root / layout).is_file():
            return {
                "match": True,
                "confidence": 1.0,
                "reason": f"Next.js App Router root layout at {layout}",
            }
    return {
        "match": False,
        "confidence": 0.2,
        "reason": "next is a dependency but no app/ root layout was found",
    }


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1])))
