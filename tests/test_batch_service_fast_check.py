import time
from src.services.batch_service import BatchService
from src.lib.config import Config


def test_fast_check_skips_delay(monkeypatch):
    # Set a large probe delay to ensure any sleep would be noticeable
    monkeypatch.setattr(Config, 'get_probe_delay_min', classmethod(lambda cls: 2.0))
    monkeypatch.setattr(Config, 'get_probe_delay_max', classmethod(lambda cls: 2.0))

    # create a fast_check that returns True for 1 and causes immediate response
    def fast_check(n):
        return n == 1

    # create check_case_exists that if called would raise (ensuring our fast_check is used)
    def slow_check(n):
        raise RuntimeError("Should not be called")

    start = time.time()
    upper, probes = BatchService.find_upper_bound(
        check_case_exists=slow_check,
        fast_check_case_exists=fast_check,
        start=1,
        probe_budget=0,
        max_probes=1,
        max_limit=1,
    )
    duration = time.time() - start
    # Ensure it returns quickly and finds upper bound 1
    assert upper == 1
    assert probes >= 0
    assert duration < 1.0  # should not have waited 2 seconds
