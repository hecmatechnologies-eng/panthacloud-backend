"""Deterministic repository pre-analysis for the analyst (CLAUDE.md §7).

Code does what code can: run each installed skill's detection test, find the manifest, and list the
known application-shell candidates. The model is given this and asked only for the residual — which
layout, the ranked candidates, the design tokens — so the expensive path is never the default one.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.skills.loader import SkillLoader

# Application-shell candidates, in order of framework convention and specificity.
_ROOT_ENTRY_POINT_CANDIDATES = (
    "app/layout.tsx",
    "app/layout.jsx",
    "app/layout.js",
    "src/app/layout.tsx",
    "src/app/layout.jsx",
    "src/app/layout.js",
    "pages/_app.tsx",
    "pages/_app.jsx",
    "pages/_app.js",
    "src/pages/_app.tsx",
    "src/pages/_app.jsx",
    "src/pages/_app.js",
    "app/root.tsx",
    "app/root.jsx",
    "src/root.tsx",
    "index.html",
    "public/index.html",
    "src/App.tsx",
    "src/App.jsx",
    "src/App.vue",
    "src/main.tsx",
    "src/main.jsx",
    "src/routes/+layout.svelte",
    "app.vue",
    "layouts/default.vue",
    "src/layouts/Layout.astro",
)

_MONOREPO_DIRS = ("apps", "packages", "modules", "frontend", "client", "web")

_STYLE_CANDIDATES = (
    "tailwind.config.js",
    "tailwind.config.ts",
    "tailwind.config.mjs",
    "tailwind.config.cjs",
    "app/globals.css",
    "src/app/globals.css",
    "styles/globals.css",
    "src/globals.css",
    "src/index.css",
    "src/App.css",
)

_IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "out",
    ".turbo",
    ".cache",
    "coverage",
    ".output",
    "vendor",
    ".venv",
    "venv",
    "__pycache__",
}

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
    style_configs: list[str] = field(default_factory=list)
    candidate_snippets: dict[str, str] = field(default_factory=dict)


def _discover_candidates(root: Path) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_if_exists(rel: str) -> None:
        norm = rel.replace("\\", "/").strip("/")
        if norm not in seen and (root / norm).is_file():
            seen.add(norm)
            candidates.append(norm)

    # 1. Root-level checks
    for pattern in _ROOT_ENTRY_POINT_CANDIDATES:
        add_if_exists(pattern)

    # 2. Monorepo / workspace package checks
    for parent_dir in _MONOREPO_DIRS:
        parent_path = root / parent_dir
        if parent_path.is_dir():
            try:
                for child in sorted(parent_path.iterdir()):
                    if child.is_dir() and child.name not in _IGNORED_DIRS:
                        child_rel = f"{parent_dir}/{child.name}"
                        for pattern in _ROOT_ENTRY_POINT_CANDIDATES:
                            add_if_exists(f"{child_rel}/{pattern}")
            except OSError:
                pass

    return candidates


def _discover_style_configs(root: Path) -> list[str]:
    styles: list[str] = []
    for pattern in _STYLE_CANDIDATES:
        norm = pattern.replace("\\", "/").strip("/")
        if (root / norm).is_file():
            styles.append(norm)

    for parent_dir in _MONOREPO_DIRS:
        parent_path = root / parent_dir
        if parent_path.is_dir():
            try:
                for child in sorted(parent_path.iterdir()):
                    if child.is_dir() and child.name not in _IGNORED_DIRS:
                        child_rel = f"{parent_dir}/{child.name}"
                        for pattern in _STYLE_CANDIDATES:
                            norm = f"{child_rel}/{pattern}"
                            if (root / norm).is_file() and norm not in styles:
                                styles.append(norm)
            except OSError:
                pass

    return styles


def _extract_snippets(root: Path, paths: list[str], max_lines: int = 60) -> dict[str, str]:
    snippets: dict[str, str] = {}
    for rel in paths:
        target = root / rel
        if target.is_file():
            try:
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
                truncated = "\n".join(lines[:max_lines])
                if len(lines) > max_lines:
                    truncated += f"\n... [{len(lines) - max_lines} more lines]"
                snippets[rel] = truncated
            except OSError:
                pass
    return snippets


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

    candidates = _discover_candidates(root)
    style_configs = _discover_style_configs(root)

    # Extract grounded snippets for top candidates and primary style config
    snippet_targets = candidates[:3] + style_configs[:1]
    snippets = _extract_snippets(root, snippet_targets)

    # Discover manifests across root and first-level workspace packages
    manifest_paths: list[str] = [name for name in _MANIFESTS if (root / name).is_file()]
    for parent_dir in _MONOREPO_DIRS:
        parent_path = root / parent_dir
        if parent_path.is_dir():
            try:
                for child in sorted(parent_path.iterdir()):
                    if child.is_dir() and child.name not in _IGNORED_DIRS:
                        pkg_file = f"{parent_dir}/{child.name}/package.json"
                        if (root / pkg_file).is_file():
                            manifest_paths.append(pkg_file)
            except OSError:
                pass

    return PreAnalysis(
        skills=matches,
        manifests=manifest_paths,
        entry_point_candidates=candidates,
        protected_paths=tuple(sorted(protected)),
        style_configs=style_configs,
        candidate_snippets=snippets,
    )
