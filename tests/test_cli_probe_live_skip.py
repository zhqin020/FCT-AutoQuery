import sys
from unittest.mock import MagicMock

from src.cli.main import FederalCourtScraperCLI


def test_probe_live_skips_case_when_tracker_says_so(monkeypatch):
    cli = FederalCourtScraperCLI()

    # Force should_skip to be True for IMM-5-21
    monkeypatch.setattr(cli.tracker, 'should_skip_case', lambda cn, force=False: (cn == 'IMM-5-21', 'no_results_repeated (3)'))

    # Ensure we would raise if the real scraper was called
    class SpyScraper:
        def __init__(self, *a, **k):
            self._initialized = True
        def initialize_page(self):
            return
        def search_case(self, case_number):
            raise AssertionError('search_case should not be invoked for skipped cases')

    monkeypatch.setattr('src.cli.main.CaseScraperService', SpyScraper)

    # Run the probe in live mode but keep it minimal and expect no searches for IMM-5-21
    sys_argv = sys.argv[:]
    try:
        sys.argv = ['prog', 'probe', '2021', '--start', '5', '--initial-high', '5', '--probe-budget', '1', '--live']
        cli.run()
    finally:
        sys.argv = sys_argv
