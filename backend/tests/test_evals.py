"""Step C · C9 — evaluation corpus and runner (FR-084–087).

The corpus covers both supported frameworks, a layout variant, an unconventional shell and a refusal.
The runner asserts on structured fields and reports per-case plus aggregate outcome, cost and wall
time. CI uses the deterministic analyzer, so no paid API is touched.
"""

from decimal import Decimal

import pytest

from app.agents.website_profile import WebsiteProfile
from app.evals.corpus import CORPUS
from app.evals.runner import AnalyzerResult, deterministic_analyze, run_corpus


def test_corpus_covers_frameworks_variants_and_a_refusal() -> None:
    assert len(CORPUS) == 5
    names = {case.name for case in CORPUS}
    assert {"nextjs-app-router", "nextjs-src-layout", "static-html"} <= names
    assert sum(1 for case in CORPUS if case.should_refuse) >= 1


@pytest.mark.asyncio
async def test_eval_runs_green_over_the_corpus() -> None:
    report = await run_corpus(deterministic_analyze)
    assert report.passed, [result for result in report.results if not result.passed]
    assert report.score == 1.0
    assert len(report.results) == 5
    assert report.total_seconds >= 0
    assert report.total_cost_usd == Decimal(0)


@pytest.mark.asyncio
async def test_eval_reports_a_failure_when_the_output_is_wrong() -> None:
    async def broken(_root) -> AnalyzerResult:
        return AnalyzerResult(WebsiteProfile(framework_skill_id="wrong-skill"))

    report = await run_corpus(broken)
    assert not report.passed
    assert report.score < 1.0
    assert any(
        "expected skill" in failure for result in report.results for failure in result.failures
    )


@pytest.mark.asyncio
async def test_a_refusal_is_a_pass_not_a_failure() -> None:
    async def always_refuses(_root) -> AnalyzerResult:
        return AnalyzerResult(WebsiteProfile(unsupported_reason="nothing to integrate"))

    report = await run_corpus(always_refuses)
    # The three success cases fail; the two refusal cases pass.
    assert not report.passed
    refusals = [r for r in report.results if r.name in {"unconventional-shell", "no-frontend"}]
    assert all(result.passed for result in refusals)


@pytest.mark.asyncio
async def test_an_analyzer_error_is_a_failed_case_not_an_abort() -> None:
    async def explodes(_root) -> AnalyzerResult:
        raise RuntimeError("boom")

    report = await run_corpus(explodes)
    assert not report.passed
    assert len(report.results) == len(CORPUS)
    assert all("analyzer raised" in result.failures[0] for result in report.results)


@pytest.mark.asyncio
async def test_cost_is_aggregated_across_cases() -> None:
    async def costly(_root) -> AnalyzerResult:
        return AnalyzerResult(
            WebsiteProfile(unsupported_reason="nothing to integrate"), cost_usd=Decimal("0.25")
        )

    report = await run_corpus(costly)
    assert report.total_cost_usd == Decimal("0.25") * len(CORPUS)
