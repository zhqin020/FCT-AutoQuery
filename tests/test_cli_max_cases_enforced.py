from src.cli.main import FederalCourtScraperCLI
from src.services.batch_service import BatchService
import pytest


def test_max_cases_limits_scan(monkeypatch):
    """If start=5 and max_cases=1 then only IMM-5-YY should be processed (linear scan bound enforced)."""
    cli = FederalCourtScraperCLI()

    # Ensure exporter.case_exists returns False for all cases: so the code attempts network search
    monkeypatch.setattr(cli.exporter, 'case_exists', lambda cn: False)

    # Replace find_upper_bound to return a larger upper to test clamping
    def fake_find_upper_bound(**kwargs):
        # Pretend we found upper bound at 1000
        return (1000, 10)

    monkeypatch.setattr(BatchService, 'find_upper_bound', staticmethod(fake_find_upper_bound))

    # Spy scraper counts searches
    class SpyScraper:
        def __init__(self, *args, **kwargs):
            self.calls = []
            self._initialized = True

        def initialize_page(self):
            return

        def search_case(self, case_number):
            self.calls.append(case_number)
            return False

    monkeypatch.setattr('src.cli.main.CaseScraperService', SpyScraper)

    cases, skipped = cli.scrape_batch_cases(year=2021, max_cases=1, start=5)

    # Because we set start=5 & max_cases=1, scanning should be limited to IMM-5-21
    # Search calls should be performed only for IMM-5-21 (as a single case number)
    spy = cli.scraper
    assert len(spy.calls) == 1
    assert spy.calls[0].endswith('-21') and spy.calls[0].startswith('IMM-5-')
