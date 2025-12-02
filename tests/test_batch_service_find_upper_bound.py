import pytest
import time
from src.services.batch_service import BatchService


def test_find_upper_bound_basic(monkeypatch):
    # make sleep and random.uniform no-op to speed up test
    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('random.uniform', lambda a,b: a)

    # check_case_exists returns True for ids 1..5
    def check_case_exists(n):
        return n <= 5

    # Ensure no persisted probe state used in this test
    monkeypatch.setattr('src.lib.config.Config.get_persist_probe_state', classmethod(lambda cls: False))
    upper, probes = BatchService.find_upper_bound(check_case_exists, start=1, probe_budget=6, max_probes=100)
    assert upper >= 5
    assert probes > 0


def test_find_upper_bound_collect(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda x: None)
    monkeypatch.setattr('random.uniform', lambda a,b: a)

    # check exists for 1..3, then 10..12 for some reason; should collect at least 3
    def check_case_exists(n):
        return n in (1,2,3)

    collected = []
    def scrape_case_data(n):
        collected.append(n)
        return {'case_id': f'case_{n}'}

    monkeypatch.setattr('src.lib.config.Config.get_persist_probe_state', classmethod(lambda cls: False))
    upper, probes = BatchService.find_upper_bound(check_case_exists, start=1, probe_budget=6, max_probes=100, collect=True, scrape_case_data=scrape_case_data, max_cases=10)
    # Should have scraped atleast the known cases
    assert len(collected) >= 3
    assert upper >= 3
