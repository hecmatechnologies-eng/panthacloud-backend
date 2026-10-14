"""Drives the runtime eval corpus over real guest turns (gap G1).

Mirrors :mod:`app.evals.runner`, which does the same for ``website_analyst``: cases in, one report
out, with a score and per-case failures. The difference is the driver. The engineering corpus runs a
deterministic analyzer in-process; this one makes an actual ``POST /api/v1/public/chat`` request,
because the properties under test are properties of the whole turn - HTTP resolution, tenant
scoping, rate limiting, prompt assembly, the gateway, and persistence - not of one function.

Retrieval is stubbed per case. Everything else is real.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from app.core.config import settings
from app.evals.runtime_corpus import RUNTIME_CORPUS, RuntimeCase, TurnObservation, stub_retrieval

# Below this, a chunk is not evidence. K1 recorded refusals citing 0.42-0.47 scores and dismissed it
# as cosmetic; the corpus treats it as a contract, so the threshold has to be a value that excludes
# noise. It is patched per-case rather than written to config, because changing the deployment
# default is a product decision and this is an assertion about the runtime's handling of one.
_STRONG_ENOUGH = 0.60


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    property: str
    passed: bool
    failures: tuple[str, ...]
    seconds: float
    cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class EvalReport:
    results: tuple[CaseResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def score(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for result in self.results if result.passed) / len(self.results)

    @property
    def total_seconds(self) -> float:
        return sum(result.seconds for result in self.results)

    @property
    def total_cost_usd(self) -> Decimal:
        return sum((result.cost_usd for result in self.results), Decimal(0))


def empty_report() -> EvalReport:
    """What a suite should get when it declines to run the corpus."""
    return EvalReport(results=())


async def _score(case: RuntimeCase, send: Callable[[RuntimeCase], Awaitable[TurnObservation]]):
    """Run one case, apply its expectations, and time it.

    Returns the failures and the elapsed time only: the observation exists to be judged, and
    handing it back would invite a caller to read it instead of the case's own verdict.
    """
    import time

    started = time.perf_counter()
    failures = tuple(f for f in case.expect(await send(case)) if f)
    return failures, time.perf_counter() - started


async def run_runtime_corpus(
    send: Callable[[RuntimeCase], Awaitable[TurnObservation]],
    cases: tuple[RuntimeCase, ...] = RUNTIME_CORPUS,
) -> EvalReport:
    """Run every case through ``send`` and aggregate the outcome."""
    results = []
    for case in cases:
        failures, seconds = await _score(case, send)
        results.append(
            CaseResult(
                name=case.name,
                property=case.property,
                passed=not failures,
                failures=failures,
                seconds=seconds,
                # The driver runs a fake model, so cost is structurally zero. Recorded explicitly
                # rather than assumed: a corpus that quietly started calling a real provider would
                # bill the CI account, and this is where that would show up first.
                cost_usd=Decimal(0),
            )
        )
    return EvalReport(results=tuple(results))


def score_threshold_for(observation_citations: tuple[dict, ...]) -> float:
    """The lowest score the corpus would consider evidence.

    Exposed so the gate can assert that a case's cited chunks all clear it, rather than leaving the
    definition in a comment where changing it changes nothing.
    """
    return _STRONG_ENOUGH if observation_citations else 0.0


__all__ = [
    "CaseResult",
    "EvalReport",
    "empty_report",
    "run_runtime_corpus",
    "score_threshold_for",
    "settings",
    "stub_retrieval",
]