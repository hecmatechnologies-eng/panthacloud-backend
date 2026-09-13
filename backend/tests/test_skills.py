"""Step C · C7 — skill packages and progressive disclosure (FR-078–083c).

The two MVP skills conform to the Agent Skills spec, expose a deterministic detection test, and
load progressively: index → SKILL.md → templates and references on demand.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from app.skills.loader import (
    Skill,
    SkillFormatError,
    SkillLoader,
    SkillMetadata,
    SkillNotFoundError,
)


@pytest.fixture
def loader() -> SkillLoader:
    return SkillLoader()


def _temp_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="c7-skill-"))
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


# ============================================================
# 1. The index and progressive disclosure
# ============================================================


def test_index_lists_the_installed_skills(loader: SkillLoader) -> None:
    index = loader.index()
    assert [metadata.id for metadata in index] == ["generic-html", "nextjs-app-router"]
    assert all(isinstance(metadata, SkillMetadata) and metadata.description for metadata in index)
    # Progressive disclosure: the index is metadata; instructions arrive only via get().
    skill = loader.get("generic-html")
    assert isinstance(skill, Skill)
    assert skill.body


def test_a_missing_skills_root_fails_loudly() -> None:
    root = Path(tempfile.mkdtemp(prefix="c7-missing-")) / "absent"
    with pytest.raises(SkillFormatError):
        SkillLoader(root=root).index()


def test_body_loads_only_on_demand(loader: SkillLoader) -> None:
    skill = loader.get("nextjs-app-router")
    assert "App Router" in skill.body
    assert skill.metadata.framework == "nextjs"
    assert skill.metadata.router == "app"


def test_assets_and_references_load_on_demand(loader: SkillLoader) -> None:
    skill = loader.get("nextjs-app-router")
    assert "fussionConfig" in skill.read_asset("FussionAssistant.tsx.j2")
    assert "src/" in skill.read_reference("EDGE-CASES.md")


def test_unknown_skill_raises(loader: SkillLoader) -> None:
    with pytest.raises(SkillNotFoundError):
        loader.get("does-not-exist")


def test_asset_path_traversal_is_refused(loader: SkillLoader) -> None:
    skill = loader.get("nextjs-app-router")
    with pytest.raises(SkillFormatError):
        skill.read_asset("../../SKILL.md")


def test_protected_paths_are_declared(loader: SkillLoader) -> None:
    metadata = loader.get("nextjs-app-router").metadata
    assert "middleware.ts" in metadata.protected_paths


# ============================================================
# 2. Deterministic detection (FR-080)
# ============================================================


def test_detection_matches_nextjs_app_router(loader: SkillLoader) -> None:
    root = _temp_repo(
        {
            "package.json": json.dumps({"dependencies": {"next": "14.0.0", "react": "18"}}),
            "app/layout.tsx": "export default function Root() { return null; }",
        }
    )
    try:
        result = loader.run_detection("nextjs-app-router", root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert result["match"] is True
    assert result["confidence"] == 1.0


def test_detection_rejects_a_non_nextjs_project(loader: SkillLoader) -> None:
    root = _temp_repo(
        {"package.json": json.dumps({"dependencies": {"react": "18"}}), "app/layout.tsx": "x"}
    )
    try:
        result = loader.run_detection("nextjs-app-router", root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert result["match"] is False


def test_detection_matches_a_static_html_site(loader: SkillLoader) -> None:
    root = _temp_repo({"index.html": "<html><body>hi</body></html>"})
    try:
        result = loader.run_detection("generic-html", root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert result["match"] is True


def test_detection_rejects_html_when_a_package_json_exists(loader: SkillLoader) -> None:
    root = _temp_repo({"index.html": "<html></html>", "package.json": "{}"})
    try:
        result = loader.run_detection("generic-html", root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert result["match"] is False


# ============================================================
# 3. The Agent Skills specification (FR-083a/083b)
# ============================================================


def test_skills_pass_the_agent_skills_validator(loader: SkillLoader) -> None:
    from skills_ref import validate

    for metadata in loader.index():
        assert validate(metadata.path) == [], metadata.id


def test_skill_body_stays_under_the_token_budget(loader: SkillLoader) -> None:
    # The spec recommends < 5000 tokens; ~4 characters per token is a safe upper bound.
    for metadata in loader.index():
        body = loader.get(metadata.id).body
        assert len(body) < 5000 * 4, metadata.id
