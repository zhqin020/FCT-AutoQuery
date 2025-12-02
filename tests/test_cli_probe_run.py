import sys
from unittest.mock import MagicMock

import pytest

from src.cli.main import FederalCourtScraperCLI
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration


class MockScraper:
    def __init__(self, *args, **kwargs):
        pass

    def initialize_page(self):
        return

    def search_case(self, case_number: str) -> bool:
        # Pretend only IMM-1-25 exists
        return case_number == 'IMM-1-25'

    def scrape_case_data(self, case_number: str):
        # Return a lightweight case-like object for tests
        class DummyCase:
            def __init__(self, cn):
                self.court_file_no = cn
                self.case_id = cn
        return DummyCase(case_number)


def test_probe_live_creates_run_and_records(monkeypatch):
    # Prepare CLI and patch components
    cli = FederalCourtScraperCLI()

    # Replace CaseScraperService with our Mock
    monkeypatch.setattr('src.cli.main.CaseScraperService', MockScraper)

    start_called = {'count': 0}
    finish_called = {'count': 0}

    def fake_start_run(self, *args, **kwargs):
        start_called['count'] += 1
        return 'probe_test_run_1'

    def fake_finish_run(self, run_id, status='completed'):
        finish_called['count'] += 1

    monkeypatch.setattr(CaseTrackingService, 'start_run', fake_start_run)
    monkeypatch.setattr(CaseTrackingService, 'finish_run', fake_finish_run)

    # Patch BatchService.find_upper_bound to return a small upper bound and ensure check function is called
    def fake_find_upper_bound(**kwargs):
        # Emulate calling check_case_exists for one case
        check = kwargs.get('check_case_exists')
        if callable(check):
            check(1)
        return (1, 1)

    monkeypatch.setattr('src.cli.main.BatchService.find_upper_bound', fake_find_upper_bound)

    # Run the CLI 'probe' command in live mode
    sys_argv = sys.argv[:]
    try:
        sys.argv = ['prog', 'probe', '2025', '--start', '1', '--live']
        cli.run()
    finally:
        sys.argv = sys_argv

    assert start_called['count'] == 1
    assert finish_called['count'] == 1


def test_scrape_without_search_starts_run(monkeypatch):
    # Validate that calling _scrape_case_data_without_search starts a run when current_run_id is None
    cli = FederalCourtScraperCLI()

    start_called = {'count': 0}
    def fake_start_run(self, *args, **kwargs):
        start_called['count'] += 1
        return 'single_test_run_1'

    # Use a mock scraper instead of None to avoid attribute errors during init
    monkeypatch.setattr('src.cli.main.CaseScraperService', MockScraper)
    monkeypatch.setattr('src.cli.main.CaseTrackingService.start_run', fake_start_run)

    # monkeypatch exporter to avoid DB operations
    class DummyCase:
        def __init__(self):
            self.court_file_no = 'IMM-527-21'
            self.case_id = 'IMM-527-21'

    cli.exporter.save_case_to_database = lambda c: ('new', None)
    recorded = {'calls': 0}
    def fake_record_case_processing(self, *args, **kwargs):
        recorded['calls'] += 1
    monkeypatch.setattr('src.cli.main.CaseTrackingService.record_case_processing', fake_record_case_processing, raising=False)

    # Call _scrape_case_data_without_search
    cli._scrape_case_data_without_search('IMM-527-21')

    assert start_called['count'] == 1
    assert recorded['calls'] >= 1
