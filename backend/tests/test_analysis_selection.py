"""Step C · C11 — choose the integration point from the analyst's ranked profile.

The candidate path is model output; `unsafe_target_reason` is tested in `test_target_paths.py`.
"""

from app.agents.website_profile import IntegrationCandidate, WebsiteProfile
from app.services.analysis.selection import (
    TARGET_CONFIDENCE_THRESHOLD,
    select_target,
)


def _candidate(path: str, confidence: float) -> IntegrationCandidate:
    return IntegrationCandidate(path=path, confidence=confidence, reason="test")


def test_selects_the_top_candidate_above_the_threshold() -> None:
    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[_candidate("app/layout.tsx", 0.9)],
    )
    selected = select_target(profile)
    assert selected is not None
    assert selected.framework_skill_id == "nextjs-app-router"
    assert selected.widget_target_path == "app/layout.tsx"


def test_declines_below_the_threshold() -> None:
    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[_candidate("app/layout.tsx", TARGET_CONFIDENCE_THRESHOLD - 0.01)],
    )
    assert select_target(profile) is None


def test_declines_when_the_repository_is_unsupported() -> None:
    profile = WebsiteProfile(unsupported_reason="No supported entry point was found.")
    assert select_target(profile) is None


def test_declines_a_framework_the_generator_cannot_build() -> None:
    profile = WebsiteProfile(
        framework_skill_id="django-magic",
        integration_candidates=[_candidate("app/layout.tsx", 0.9)],
    )
    assert select_target(profile) is None


def test_skips_unsafe_candidates_and_uses_the_next_safe_one() -> None:
    profile = WebsiteProfile(
        framework_skill_id="generic-html",
        integration_candidates=[
            _candidate("../etc/passwd", 0.99),
            _candidate("/etc/passwd", 0.98),
            _candidate(".github/workflows/deploy.yml", 0.97),
            _candidate("index.html", 0.9),
        ],
    )
    selected = select_target(profile)
    assert selected is not None
    assert selected.widget_target_path == "index.html"


def test_verification_gate_rejects_hallucinated_candidate_and_picks_existing(tmp_path) -> None:
    # Physical file setup: only app/layout.tsx exists, src/app/layout.tsx is hallucinated
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "layout.tsx").write_text("export default function Root() {}", encoding="utf-8")

    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[
            _candidate("src/app/layout.tsx", 0.95),  # Does not exist on disk
            _candidate("app/layout.tsx", 0.85),      # Real physical file
        ],
    )
    selected = select_target(profile, workspace_path=tmp_path)
    assert selected is not None
    assert selected.widget_target_path == "app/layout.tsx"
    assert selected.confidence == 0.85


def test_verification_gate_rejects_empty_candidate(tmp_path) -> None:
    (tmp_path / "index.html").write_text("", encoding="utf-8")  # Empty file

    profile = WebsiteProfile(
        framework_skill_id="generic-html",
        integration_candidates=[_candidate("index.html", 0.95)],
    )
    assert select_target(profile, workspace_path=tmp_path) is None


def test_verification_gate_declines_when_all_candidates_hallucinated(tmp_path) -> None:
    profile = WebsiteProfile(
        framework_skill_id="nextjs-app-router",
        integration_candidates=[
            _candidate("app/layout.tsx", 0.95),
            _candidate("src/app/layout.tsx", 0.90),
        ],
    )
    # Neither candidate exists in tmp_path
    assert select_target(profile, workspace_path=tmp_path) is None

