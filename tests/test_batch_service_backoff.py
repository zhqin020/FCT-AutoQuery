from src.services.batch_service import BatchService
from src.lib.rate_limiter import EthicalRateLimiter


def test_find_upper_bound_handles_transient_exceptions_and_uses_backoff():
    calls = {"count": 0}

    def flaky_check(n: int):
        # raise exception on first two calls to simulate transient failures
        calls["count"] += 1
        if calls["count"] <= 2:
            raise Exception("transient")
        # afterwards, return False for high and True for small ids
        return n < 10

    rl = EthicalRateLimiter(interval_seconds=0.0)
    # run probe with the flaky check
    upper, probes = BatchService.find_upper_bound(flaky_check, start=1, initial_high=16, probe_budget=50, rate_limiter=rl)

    # Ensure the function completed and used probes
    assert isinstance(upper, int)
    assert probes >= 3
    # The rate limiter should have recorded failures
    assert rl.failure_count >= 2
