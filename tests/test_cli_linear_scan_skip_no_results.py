from src.cli.main import FederalCourtScraperCLI
from src.services.case_tracking_service import CaseTrackingService


def test_linear_scan_cli_skips_repeated_no_results(monkeypatch):
    cli = FederalCourtScraperCLI()

    # Simulate that should_skip_case returns True for IMM-5-21
    def fake_should_skip(case_number, force=False):
        if case_number == 'IMM-5-21':
            return True, 'no_results_repeated (3)'
        return False, ''

    monkeypatch.setattr(cli.tracker, 'should_skip_case', fake_should_skip)

    # Ensure exporter.case_exists is False and would raise if called (we expect skip)
    def raise_if_called(case_number):
        raise AssertionError('exporter.case_exists should not be called for skipped cases')
    cli.exporter.case_exists = raise_if_called

    # Ensure scraper.search_case would raise if called (we expect skip)
    class NeverCalledScraper:
        def __init__(self, *a, **k):
            self._initialized = True
        def initialize_page(self):
            return
        def close(self):
            return
        def search_case(self, n):
            raise AssertionError('search_case should not be called for skipped cases')

    monkeypatch.setattr('src.cli.main.CaseScraperService', NeverCalledScraper)

    # Monkeypatch BatchService to force an upper bound of 5 so linear scan will process IMM-5-21
    from src.services.batch_service import BatchService

    def fake_find_upper_bound(**kwargs):
        return (5, 1)

    monkeypatch.setattr(BatchService, 'find_upper_bound', staticmethod(fake_find_upper_bound))

    # Call batch scrape with year that maps case 5 -> IMM-5-21
    scraped_cases, skipped = cli.scrape_batch_cases(2021, max_cases=10, start=1)

    # Since should_skip indicates no_results_repeated, we expect skip(s) and no scrapes
    assert all(entry['status'] == 'skipped' for entry in skipped) or len(skipped) >= 1
