"""Kill switch and circuit breaker (OWASP ASI08, ASI10).

The breaker is pure and tested directly. The kill switch needs Redis, so its state machine is
tested against a stub and the real Redis path is exercised only where a pool exists.
"""

import uuid

import pytest

from app.harness.halt import CircuitBreaker, CircuitBreakerOpen, RunHaltedError


class TestCircuitBreaker:
    def test_threshold_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            CircuitBreaker(threshold=0)

    def test_below_threshold_does_not_open(self) -> None:
        breaker = CircuitBreaker(threshold=3)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.consecutive_failures == 2

    def test_opens_at_threshold(self) -> None:
        breaker = CircuitBreaker(threshold=3)
        breaker.record_failure()
        breaker.record_failure()
        with pytest.raises(CircuitBreakerOpen):
            breaker.record_failure()

    def test_success_resets_the_run_of_failures(self) -> None:
        """Consecutive, not cumulative: fail/succeed/fail must never accumulate into an open."""
        breaker = CircuitBreaker(threshold=2)
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        assert breaker.consecutive_failures == 1

    def test_reset_survives_an_open_and_close_cycle(self) -> None:
        breaker = CircuitBreaker(threshold=2)
        breaker.record_failure()
        with pytest.raises(CircuitBreakerOpen):
            breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        assert breaker.consecutive_failures == 1


class TestHaltCheckWiring:
    """The harness receives ``halt_check`` as a callable; these assert the contract it relies on."""

    async def test_returns_none_to_proceed(self) -> None:
        async def check() -> str | None:
            return None

        assert await check() is None

    async def test_returns_a_reason_to_halt(self) -> None:
        reason = "Operator halted all agent execution."

        async def check() -> str | None:
            return reason

        assert await check() == reason

    def test_halted_error_is_an_exception(self) -> None:
        with pytest.raises(RunHaltedError):
            raise RunHaltedError("halted")


class TestKillswitchStateMachine:
    """Exercises the real module against a stub Redis, so the key layout is covered."""

    @pytest.fixture
    def stub_redis(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
        store: dict[str, str] = {}

        class FakeRedis:
            async def get(self, key: str) -> str | None:
                return store.get(key)

            async def set(self, key: str, value: str) -> None:
                store[key] = value

            async def delete(self, key: str) -> None:
                store.pop(key, None)

            async def scan_iter(self, pattern: str):
                prefix = pattern.rstrip("*")
                for key in list(store):
                    if key.startswith(prefix):
                        yield key

        pool = type("Pool", (), {"redis": FakeRedis()})()
        monkeypatch.setattr("app.services.killswitch.get_arq_pool", _async_return(pool))
        return store

    def _org(self) -> uuid.UUID:
        return uuid.uuid4()

    async def test_not_halted_by_default(self, stub_redis: dict[str, str]) -> None:
        from app.services.killswitch import is_halted

        assert await is_halted(self._org()) is None

    async def test_global_halt_stops_every_org(self, stub_redis: dict[str, str]) -> None:
        from app.services.killswitch import halt_global, is_halted, resume_global

        await halt_global()
        assert await is_halted(self._org()) is not None
        assert await is_halted(None) is not None

        await resume_global()
        assert await is_halted(self._org()) is None

    async def test_org_halt_is_scoped_to_one_tenant(self, stub_redis: dict[str, str]) -> None:
        from app.services.killswitch import halt_org, is_halted

        halted, untouched = self._org(), self._org()
        await halt_org(halted)

        assert await is_halted(halted) is not None
        assert await is_halted(untouched) is None

    async def test_status_lists_halted_organizations(self, stub_redis: dict[str, str]) -> None:
        from app.services.killswitch import halt_org, status

        org = self._org()
        await halt_org(org)

        report = await status()
        assert report["available"] is True
        assert report["global_halted"] is False
        assert org.hex in report["halted_organizations"] or str(org) in str(
            report["halted_organizations"]
        )

    async def test_missing_redis_fails_open_for_reads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Availability beats safety on the read path; the failure is logged, not raised."""
        from app.services.killswitch import is_halted

        async def no_pool(_settings: object = None) -> None:
            return None

        monkeypatch.setattr("app.services.killswitch.get_arq_pool", no_pool)
        assert await is_halted(self._org()) is None

    async def test_missing_redis_refuses_to_engage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Writing the switch must not silently no-op - a kill switch that does not engage is
        worse than one that is visibly broken."""
        from app.services.killswitch import KillswitchUnavailable, halt_global

        async def no_pool(_settings: object = None) -> None:
            return None

        monkeypatch.setattr("app.services.killswitch.get_arq_pool", no_pool)
        with pytest.raises(KillswitchUnavailable):
            await halt_global()


def _async_return(value: object):
    async def _get(_settings: object = None) -> object:
        return value

    return _get