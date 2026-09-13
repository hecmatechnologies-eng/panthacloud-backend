"""The WebsiteAnalyst's structured output (AGENT-ARCHITECTURE §3.2).

Two contract decisions, deliberately:

- ``integration_candidates`` is a **ranked list**, never a single path. Below a confidence threshold
  the Studio presents the alternatives and a human chooses; a single answer forces the agent to
  guess.
- ``unsupported_reason`` is a **first-class successful outcome**, not an error path. An analyst that
  guesses on an unrecognisable repository is worse than one that declines.
"""

from pydantic import BaseModel, Field, model_validator


class IntegrationCandidate(BaseModel):
    path: str = Field(..., description="Repository-relative path of a possible integration point.")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str


class DesignTokens(BaseModel):
    primary_color: str | None = None
    radius: str | None = None
    font_family: str | None = None
    spacing_unit: str | None = None


class WebsiteProfile(BaseModel):
    framework_skill_id: str | None = Field(
        None, description="Id of the matched skill package, or null if none matched."
    )
    router: str | None = None
    language: str | None = None
    package_manager: str | None = None
    build_command: str | None = None
    entry_points: list[str] = Field(default_factory=list)
    integration_candidates: list[IntegrationCandidate] = Field(default_factory=list)
    styling_system: str | None = None
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    protected_paths: list[str] = Field(default_factory=list)
    unsupported_reason: str | None = Field(
        None, description="Set when the repository cannot be integrated safely; the run still succeeds."
    )

    @model_validator(mode="after")
    def _refusal_excludes_candidates(self) -> "WebsiteProfile":
        if self.unsupported_reason and self.integration_candidates:
            raise ValueError(
                "unsupported_reason must not be combined with integration_candidates."
            )
        return self
