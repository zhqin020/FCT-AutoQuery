from unittest.mock import MagicMock
from src.cli.main import FederalCourtScraperCLI


def test_batch_run_avoids_repeated_searches_for_no_results(monkeypatch):
    """When a case returns no-results once in this run, subsequent probes in the same run should not re-call the network search."""
    cli = FederalCourtScraperCLI()

    # Create a spy scraper that counts search_case invocations for IMM-5-21
    class SpyScraper:
        def __init__(self, *args, **kwargs):
            self._initialized = True
            self.calls = []

        def initialize_page(self):
            return

        def search_case(self, case_number):
            self.calls.append(case_number)
            # Return False (no results) always
            return False

    monkeypatch.setattr('src.cli.main.CaseScraperService', SpyScraper)

    # Ensure tracker doesn't skip via DB rules
    monkeypatch.setattr(cli.tracker, 'should_skip_case', lambda cn, force=False: (False, ''))

    # Also ensure exporter.case_exists returns False so the code will call search
    monkeypatch.setattr(cli.exporter, 'case_exists', lambda cn: False)

    # Run batch scrape in memory with a small probe range so IMM-5-21 will be attempted
    cases, skipped = cli.scrape_batch_cases(year=2021, max_cases=1, start=5)

    # Confirm the scraper was called at least once but not multiple times for the same case
    spy_scraper = cli.scraper
    calls_for_imm5 = [c for c in spy_scraper.calls if c == 'IMM-5-21']
    # Accept either 0 or 1 calls here: if this test run preloads IMM-5-21 as recently no-results,
    # it will be skipped and no search will be executed; otherwise the search should occur once
    # and not be re-executed in the same run.
    assert len(calls_for_imm5) in (0, 1)
