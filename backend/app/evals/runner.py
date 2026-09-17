"""Evaluation runner (FR-085, FR-086).

Runs an analyzer across the golden corpus and asserts on **structured output fields**, never exact
strings. Reports per-case pass/fail plus aggregate score, cost and wall time.

The analyzer is injected and asynchronous. CI uses the deterministic pre-analysis
(``deterministic_analyze``), so no paid API is touched; a real-model run passes
``harness_analyzer(...)``, which drives the WebsiteAnalyst through the harness.
"""

import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.website_profile import IntegrationCandidate, WebsiteProfile
from app.evals.corpus import CORPUS, EvalCase
from app.harness.context import ExecutionContext
from app.harness.runner import AgentRunner
from app.llm.gateway import ModelGateway
from app.models.agent_run import AgentToolCall
from app.services.analysis.analyst import analyze_repository
from app.services.analysis.pre_analysis import pre_analyze
from app.skills.loader import SkillLoader
from app.tools.gateway import ToolGateway
from app.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    profile: WebsiteProfile | None
    cost_usd: Decimal = Decimal(0)
    # What the case cost, for the budget ceilings on `EvalCase`. A model-free analyzer reports
    # zeroes, and a ceiling is only asserted against a figure the analyzer actually measured.
    total_tokens: int = 0
    tool_calls: int = 0


Analyzer = Callable[[Path], Awaitable[AnalyzerResult]]


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    cost_usd: Decimal = Decimal(0)
    seconds: float = 0.0
    total_tokens: int = 0
    tool_calls: int = 0


@dataclass(frozen=True, slots=True)
class EvalReport:
    results: list[CaseResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def score(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for result in self.results if result.passed) / len(self.results)

    @property
    def total_cost_usd(self) -> Decimal:
        return sum((result.cost_usd for result in self.results), Decimal(0))

    @property
    def total_seconds(self) -> float:
        return round(sum(result.seconds for result in self.results), 4)


async def run_corpus(
    analyzer: Analyzer, cases: tuple[EvalCase, ...] = CORPUS
) -> EvalReport:
    results: list[CaseResult] = []
    for case in cases:
        root = _materialize(case)
        started = time.perf_counter()
        output = AnalyzerResult(None)
        try:
            output = await analyzer(root)
            failures = _check(case, output)
        except Exception as exc:  # noqa: BLE001 — an erroring case is a failed case, not an abort
            failures = [f"analyzer raised: {exc}"]
        finally:
            shutil.rmtree(root, ignore_errors=True)
        results.append(
            CaseResult(
                name=case.name,
                passed=not failures,
                failures=failures,
                cost_usd=output.cost_usd,
                seconds=round(time.perf_counter() - started, 4),
                total_tokens=output.total_tokens,
                tool_calls=output.tool_calls,
            )
        )
    return EvalReport(results)


async def deterministic_analyze(repo_root: Path) -> AnalyzerResult:
    """A model-free analyzer: the deterministic detection the analyst is grounded on."""
    pre = pre_analyze(repo_root)
    if not pre.skills:
        return AnalyzerResult(
            WebsiteProfile(
                unsupported_reason="No supported framework or static HTML entry point was detected."
            )
        )
    top = pre.skills[0]
    candidates = [
        IntegrationCandidate(
            path=path,
            confidence=round(max(0.3, 0.9 - index * 0.2), 2),
            reason="application-shell candidate",
        )
        for index, path in enumerate(pre.entry_point_candidates)
    ]
    return AnalyzerResult(
        WebsiteProfile(
            framework_skill_id=top.skill_id,
            entry_points=list(pre.entry_point_candidates),
            integration_candidates=candidates,
            protected_paths=list(pre.protected_paths),
        )
    )


def harness_analyzer(
    *,
    db: AsyncSession,
    context: ExecutionContext,
    runner: AgentRunner,
    gateway: ModelGateway,
    tool_gateway: ToolGateway,
    registry: ToolRegistry,
    loader: SkillLoader | None = None,
) -> Analyzer:
    """An analyzer that drives the real WebsiteAnalyst through the harness (for manual runs).

    This is the analyzer the budget ceilings are written for: `deterministic_analyze` costs nothing
    and reports nothing, so the ceilings are inert in CI and live wherever a real model runs.
    """

    async def analyze(repo_root: Path) -> AnalyzerResult:
        run, profile = await analyze_repository(
            db,
            context=context,
            repo_root=repo_root,
            runner=runner,
            gateway=gateway,
            tool_gateway=tool_gateway,
            registry=registry,
            loader=loader,
        )
        # Counted rather than read off `run.tool_calls`: that relationship is lazily loaded, and
        # touching it here would raise under the async session.
        tool_calls = await db.scalar(
            select(func.count())
            .select_from(AgentToolCall)
            .where(AgentToolCall.agent_run_id == run.id)
        )
        return AnalyzerResult(
            profile,
            run.cost_usd,
            total_tokens=run.tokens_used,
            tool_calls=tool_calls or 0,
        )

    return analyze


def _check(case: EvalCase, output: AnalyzerResult) -> list[str]:
    """Assert the case's expected profile *and* its budget ceilings.

    A ceiling is only asserted when the analyzer reported a non-zero figure, so the model-free
    analyzer used in CI (which reports nothing) is not held to a model's budget — and a real run is.
    """
    failures = _check_budget(case, output)
    profile = output.profile
    if case.should_refuse:
        if profile is None or not profile.unsupported_reason:
            return failures + ["expected a refusal, but a profile was produced"]
        if profile.integration_candidates:
            return failures + ["a refusal must not also carry integration candidates"]
        return failures
    if profile is None:
        return failures + ["no profile was produced"]
    if profile.unsupported_reason:
        failures.append(f"unexpected refusal: {profile.unsupported_reason}")
    if case.expect_skill_id is not None and profile.framework_skill_id != case.expect_skill_id:
        failures.append(
            f"expected skill {case.expect_skill_id!r}, got {profile.framework_skill_id!r}"
        )
    if not profile.integration_candidates:
        failures.append("no integration candidates were returned")
    elif case.expect_candidate is not None and case.expect_candidate not in [
        candidate.path for candidate in profile.integration_candidates
    ]:
        failures.append(f"expected candidate {case.expect_candidate!r} was not ranked")
    return failures


def _check_budget(case: EvalCase, output: AnalyzerResult) -> list[str]:
    """The performance gate: a case that costs more than its ceiling fails, it does not warn.

    Without this the suite measured tokens and wall-clock but asserted nothing, which is how the
    analyst's search cost went unnoticed while it took 11-23s per call on a real repository.
    """
    failures: list[str] = []
    if case.max_tokens is not None and output.total_tokens > case.max_tokens:
        failures.append(
            f"used {output.total_tokens} tokens, over the {case.max_tokens} ceiling"
        )
    if case.max_tool_calls is not None and output.tool_calls > case.max_tool_calls:
        failures.append(
            f"made {output.tool_calls} tool calls, over the {case.max_tool_calls} ceiling"
        )
    return failures


def _materialize(case: EvalCase) -> Path:
    root = Path(tempfile.mkdtemp(prefix=f"fussion-eval-{case.name}-"))
    for relative, content in case.files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root
