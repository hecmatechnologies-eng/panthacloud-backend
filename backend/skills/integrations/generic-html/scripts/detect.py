"""Deterministic detection for the generic-html skill (FR-080).

Self-contained: prints a JSON object `{"match", "confidence", "reason"}` for a repository root.
"""

import json
import sys
from pathlib import Path


def detect(repo_root: str | Path) -> dict:
    root = Path(repo_root)
    package = root / "package.json"
    if package.is_file():
        return {
            "match": False,
            "confidence": 0.0,
            "reason": "package.json present; this is not a static HTML site",
        }

    for html in ("index.html", "public/index.html"):
        if (root / html).is_file():
            return {
                "match": True,
                "confidence": 1.0,
                "reason": f"static HTML entry point at {html}",
            }
    return {"match": False, "confidence": 0.0, "reason": "no index.html found"}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1])))
