"""Skill packages and progressive disclosure (FR-078–083c).

Framework integration knowledge lives in `skills/integrations/<id>/` as Agent Skills packages, not
in application code. This loader reads the index (name + description only — the always-on tier),
loads a matched `SKILL.md` on demand, and reads templates and references only when referenced.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.config import settings

_DETECTION_TIMEOUT_SECONDS = 30


def _default_root() -> Path:
    if settings.SKILLS_ROOT:
        return Path(settings.SKILLS_ROOT)
    # `app/skills/loader.py` -> parents[3] is the repository root, which holds skills/.
    return Path(__file__).resolve().parents[3] / "skills" / "integrations"


class SkillNotFoundError(Exception):
    """No skill is installed under the requested id."""


class SkillFormatError(Exception):
    """A skill package does not follow the Agent Skills specification."""


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    """The always-on tier: everything needed to decide whether a skill applies."""

    id: str
    description: str
    path: Path
    framework: str | None
    router: str | None
    version: str | None
    protected_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Skill:
    metadata: SkillMetadata
    body: str

    def read_asset(self, relative_path: str) -> str:
        return _read_within(self.metadata.path / "assets", relative_path)

    def read_reference(self, relative_path: str) -> str:
        return _read_within(self.metadata.path / "references", relative_path)


class SkillLoader:
    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else _default_root()

    def index(self) -> list[SkillMetadata]:
        """Every installed skill's metadata, without loading any body (FR-081)."""
        if not self._root.is_dir():
            # Fail loudly rather than report an empty catalogue for a missing install.
            raise SkillFormatError(
                f"Skills root does not exist: {self._root}. Set SKILLS_ROOT or install skills/."
            )
        return [
            self._metadata(path)
            for path in sorted(self._root.iterdir())
            if (path / "SKILL.md").is_file()
        ]

    def get(self, skill_id: str) -> Skill:
        metadata = self._find(skill_id)
        _front, body = _parse_skill_md(metadata.path / "SKILL.md")
        return Skill(metadata=metadata, body=body)

    def run_detection(self, skill_id: str, repo_root: Path) -> dict:
        """Run the skill's deterministic detection test against a repository root (FR-080)."""
        metadata = self._find(skill_id)
        script = metadata.path / "scripts" / "detect.py"
        if not script.is_file():
            return {"match": False, "confidence": 0.0, "reason": "no detection script"}
        try:
            result = subprocess.run(
                [sys.executable, str(script), str(repo_root)],
                capture_output=True,
                text=True,
                check=False,
                timeout=_DETECTION_TIMEOUT_SECONDS,
                # A scrubbed environment: the detection script needs no DB URL, JWT or API key.
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                },
            )
        except subprocess.TimeoutExpired:
            return {"match": False, "confidence": 0.0, "reason": "detection timed out"}
        except OSError as exc:
            return {"match": False, "confidence": 0.0, "reason": f"detection could not run: {exc}"}
        if result.returncode != 0:
            return {
                "match": False,
                "confidence": 0.0,
                "reason": f"detection failed: {result.stderr[:200]}",
            }
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"match": False, "confidence": 0.0, "reason": "detection output was not JSON"}
        if not isinstance(parsed, dict):
            return {
                "match": False,
                "confidence": 0.0,
                "reason": "detection output was not an object",
            }
        return parsed

    def _find(self, skill_id: str) -> SkillMetadata:
        for metadata in self.index():
            if metadata.id == skill_id:
                return metadata
        raise SkillNotFoundError(f"No skill named {skill_id!r} is installed.")

    def _metadata(self, path: Path) -> SkillMetadata:
        front, _body = _parse_skill_md(path / "SKILL.md")
        name = front.get("name")
        if name != path.name:
            raise SkillFormatError(
                f"{path}: frontmatter name {name!r} must match the directory name {path.name!r}."
            )
        description = front.get("description")
        if not description:
            raise SkillFormatError(f"{path}: frontmatter description is required.")
        metadata = front.get("metadata") or {}
        return SkillMetadata(
            id=name,
            description=description,
            path=path,
            framework=metadata.get("fussion.framework"),
            router=metadata.get("fussion.router"),
            version=metadata.get("fussion.version"),
            protected_paths=_split_paths(metadata.get("fussion.protected-paths")),
        )


def _parse_skill_md(path: Path) -> tuple[dict, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillFormatError(f"{path}: SKILL.md must start with YAML frontmatter.")
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        raise SkillFormatError(f"{path}: SKILL.md frontmatter is not closed.")
    front = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(front, dict):
        raise SkillFormatError(f"{path}: frontmatter must be a mapping.")
    return front, "\n".join(lines[end + 1 :]).lstrip("\n")


def _split_paths(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _read_within(base: Path, relative_path: str) -> str:
    target = (base / relative_path).resolve()
    if not target.is_relative_to(base.resolve()):
        raise SkillFormatError(f"Refused path {relative_path!r}: it escapes the skill directory.")
    return target.read_text(encoding="utf-8")
