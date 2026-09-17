"""Choose the integration point from the analyst's ranked profile (step C11).

The analyst returns a *ranked* list of integration candidates, never a single path: below a
confidence threshold the Studio shows the alternatives and a human chooses (see `WebsiteProfile`).
This module turns that ranked output into the one decision the deterministic pipeline needs — the
framework skill id and the widget target path — or declines to decide.

The candidate path is model output, so it is untrusted (`CLAUDE.md` §4.5). It is checked with the
same gate the configuration schema applies (`app.core.target_paths`), so a path reaches the
integration only if it is repository-relative, traversal-free and not protected.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.agents.website_profile import IntegrationCandidate, WebsiteProfile
from app.core.target_paths import unsafe_target_reason
from app.models.website_integration import KNOWN_FRAMEWORK_SKILL_IDS

logger = logging.getLogger("fussion.analysis.selection")

# Below this, the top candidate is not good enough to configure a customer's repository without a
# human choosing. A guess here writes to a real repository, so the bar is deliberately modest but
# non-zero.
TARGET_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True)
class SelectedTarget:
    """The integration point the analyst's profile justifies, and the confidence it rested on."""

    framework_skill_id: str
    widget_target_path: str
    confidence: float


def select_target(
    profile: WebsiteProfile,
    workspace_path: Path | None = None,
) -> SelectedTarget | None:
    """The integration target the profile justifies, or None.

    None means "do not configure automatically": the repository was refused, no candidate clears the
    threshold, the framework matched no buildable skill, or every candidate is an unsafe path. In
    each case the Studio shows the ranked list and a human decides.

    If ``workspace_path`` is provided, candidates are validated against the physical filesystem:
    hallucinated paths that do not exist or are unreadable are rejected in favor of the next ranked
    candidate.
    """
    if profile.unsupported_reason:
        return None
    if profile.framework_skill_id not in KNOWN_FRAMEWORK_SKILL_IDS:
        return None
    top = _top_safe_candidate(profile.integration_candidates, workspace_path=workspace_path)
    if top is None or top.confidence < TARGET_CONFIDENCE_THRESHOLD:
        return None
    return SelectedTarget(
        framework_skill_id=profile.framework_skill_id,
        widget_target_path=top.path.strip(),
        confidence=top.confidence,
    )


def _top_safe_candidate(
    candidates: list[IntegrationCandidate],
    workspace_path: Path | None = None,
) -> IntegrationCandidate | None:
    ranked = sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)
    for candidate in ranked:
        clean_path = candidate.path.strip()
        if unsafe_target_reason(clean_path) is not None:
            continue
        if workspace_path is not None:
            target_file = workspace_path / clean_path
            if not target_file.is_file():
                logger.warning(
                    "Rejecting non-existent candidate target path '%s' (potential hallucination)",
                    clean_path,
                )
                continue
            try:
                content = target_file.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    logger.warning("Rejecting empty candidate target file '%s'", clean_path)
                    continue
            except OSError:
                continue
        return candidate
    return None
