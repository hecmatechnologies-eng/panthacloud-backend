"""Deterministic repository pre-analysis for the analyst (CLAUDE.md §7).

Code does what code can: run each installed skill's detection test, find the manifest, and list the
known application-shell candidates. The model is given this and asked only for the residual — which
layout, the ranked candidates, the design tokens — so the expensive path is never the default one.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.skills.loader import SkillLoader

# Application-shell candidates, in the order a Next.js project would present them.
_ENTRY_POINT_CANDIDATES = (
    "app/layout.tsx",
    "app/layout.jsx",
    "src/app/layout.tsx",
    "src/app/layout.jsx",
    "pages/_app.tsx",
    "src/pages/_app.tsx",
    "index.html",
    "public/index.html",
)

_MANIFESTS = ("package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json")


@dataclass(frozen=True, slots=True)
class SkillMatch:
    skill_id: str
    version: str | None
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class PreAnalysis:
    skills: list[SkillMatch] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    entry_point_candidates: list[str] = field(default_factory=list)
    protected_paths: tuple[str, ...] = ()


def pre_analyze(repo_root: Path, loader: SkillLoader | None = None) -> PreAnalysis:
    root = Path(repo_root)
    loader = loader or SkillLoader()

    matches: list[SkillMatch] = []
    protected: set[str] = set()
    for metadata in loader.index():
        result = loader.run_detection(metadata.id, root)
        if result.get("match"):
            matches.append(
                SkillMatch(
                    skill_id=metadata.id,
                    version=metadata.version,
                    confidence=float(result.get("confidence", 0.0)),
                    reason=str(result.get("reason", "")),
                )
            )
            protected.update(metadata.protected_paths)
    matches.sort(key=lambda match: match.confidence, reverse=True)

    return PreAnalysis(
        skills=matches,
        manifests=[name for name in _MANIFESTS if (root / name).is_file()],
        entry_point_candidates=[
            path for path in _ENTRY_POINT_CANDIDATES if (root / path).is_file()
        ],
        protected_paths=tuple(sorted(protected)),
    )
