from src.services.batch_service import BatchService


def test_linear_scan_fast_db_check_does_not_scrape(monkeypatch):
    calls = {"scraped": False}

    def fake_scrape_case_data(n):
        calls["scraped"] = True
        return None

    # fast_check returns True for numbers 1 and 2 (so last_success will be 1, and linear scan will see 2)
    def fast_check(n):
        return n in (1, 2)

    # check_case_exists should not be called for the fast path; if it is, this indicates a regression
    def check_case_exists(n):
        raise AssertionError("check_case_exists should not be called for fast DB check during linear scan")

    upper, probes = BatchService.find_upper_bound(
        check_case_exists=check_case_exists,
        fast_check_case_exists=fast_check,
        start=1,
        initial_high=1,
        probe_budget=2,
        collect=True,
        scrape_case_data=fake_scrape_case_data,
        max_probes=10,
    )

    # If the linear scan's fast check avoided calling scrape_case_data, the flag should be False
    assert calls["scraped"] is False
