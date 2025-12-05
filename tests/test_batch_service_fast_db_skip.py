from src.services.batch_service import BatchService
from src.cli.tracking_integration import create_tracking_integrated_check_exists
from src.cli.main import FederalCourtScraperCLI


def test_fast_db_check_does_not_scrape(monkeypatch):
    calls = {"scraped": False}

    def fake_scrape_case_data(n):
        calls["scraped"] = True
        return None

    # fast_check returns True for 1 and False otherwise
    def fast_check(n):
        return n == 1

    # check_case_exists should never be called in this scenario for n=1
    def check_case_exists(n):
        raise AssertionError("check_case_exists should not be called for fast DB check")

    upper, probes = BatchService.find_upper_bound(
        check_case_exists=check_case_exists,
        fast_check_case_exists=fast_check,
        start=1,
        initial_high=2,
        probe_budget=2,
        collect=True,
        scrape_case_data=fake_scrape_case_data,
        max_probes=10,
    )

    assert calls["scraped"] is False


def test_cli_check_skips_no_results_repeated(monkeypatch):
    cli = FederalCourtScraperCLI()
    # Stub tracker.should_skip_case to return True indicating repeated no results
    monkeypatch.setattr(cli, 'tracker', cli.tracker)
    monkeypatch.setattr(cli.tracker, 'should_skip_case', lambda cn, force=False: (True, 'no_data_repeated (3)'))
    # Ensure exporter case_exists is not called; set it to raise if invoked
    def raise_on_exporter(*args, **kwargs):
        raise AssertionError('exporter.case_exists should not be called')
    cli.exporter.case_exists = raise_on_exporter
    # Also ensure scraper.search_case would raise if called
    cli.scraper = None
    cli.scraper = type('S', (), {'search_case': lambda self, x: (_ for _ in ()).throw(AssertionError('search_case should not be called'))})()

    # Capture record_case_processing calls
    recorded = {'outcome': None}
    def fake_record_case_processing(self, *args, **kwargs):
        recorded['outcome'] = kwargs.get('outcome') or (args[3] if len(args) > 3 else None)
    monkeypatch.setattr('src.cli.main.CaseTrackingService.record_case_processing', fake_record_case_processing, raising=False)

    check = create_tracking_integrated_check_exists(cli, run_id='r1', year=2025)
    assert check(5) is False
    # Ensure skip was recorded as 'skipped' not 'no_data'
    assert recorded['outcome'] == 'skipped'
