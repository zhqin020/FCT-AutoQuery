import time

from src.lib.rate_limiter import EthicalRateLimiter


def test_backoff_increases_on_consecutive_failures():
    rl = EthicalRateLimiter(interval_seconds=0.0)
    rl.backoff_factor = 1.0
    rl.max_backoff_seconds = 100.0

    d1 = rl.record_failure()
    d2 = rl.record_failure()
    d3 = rl.record_failure()

    assert d1 > 0
    assert d2 >= d1 * 2 - 1e-6
    assert d3 >= d2 * 2 - 1e-6


def test_backoff_caps_at_max_backoff():
    rl = EthicalRateLimiter(interval_seconds=0.0)
    rl.backoff_factor = 10.0
    rl.max_backoff_seconds = 5.0

    # Repeated failures should not exceed max_backoff_seconds
    delays = [rl.record_failure() for _ in range(6)]
    assert all(d <= rl.max_backoff_seconds + 1e-6 for d in delays)


def test_record_failure_with_status_code_strengthens_backoff():
    rl = EthicalRateLimiter(interval_seconds=0.0)
    rl.backoff_factor = 1.0
    rl.max_backoff_seconds = 100.0

    d1 = rl.record_failure(status_code=500)
    rl.reset_failures()
    d2 = rl.record_failure(status_code=429)

    assert d2 >= d1
