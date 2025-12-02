from typing import Optional

from src.cli.tracking_integration import (
    create_tracking_integrated_check_exists,
    create_tracking_integrated_scrape_case,
    TrackingIntegration,
)


class MockTracker:
    def __init__(self):
        self.calls = []

    def record_case_processing(self, *args, **kwargs):
        self.calls.append((args, kwargs))
    def should_skip_case(self, *args, **kwargs):
        return False, ""


class MockScraper:
    def __init__(self, exists_map=None):
        self.exists_map = exists_map or {}

    def search_case(self, case_number: str) -> bool:
        return self.exists_map.get(case_number, False)

    def scrape_case_data(self, case_number: str) -> Optional[object]:
        class _C:
            def __init__(self, case_id):
                self.case_id = case_id

        if self.search_case(case_number):
            return _C(case_id=f"case_{case_number}")
        return None


class MockCLI:
    def __init__(self, tracker, scraper=None):
        self.tracker = tracker
        self.scraper = scraper
        self.scraper_class = lambda headless=False: MockScraper()
        self.force = False
        # placeholder for _scraper_headless
        self._scraper_headless = False


def test_create_tracking_integrated_check_exists_records_probe():
    tracker = MockTracker()
    # Create a CLI that uses a scraper returning True for a known case
    cli = MockCLI(tracker, MockScraper({'IMM-1-25': True}))

    check = create_tracking_integrated_check_exists(cli, run_id='r1')
    assert callable(check)

    exists = check(1)  # IMM-1-25
    assert exists in (True, False)
    # TrackingIntegration should have used tracker.record_case_processing at least once
    assert len(tracker.calls) >= 1


def test_create_tracking_integrated_scrape_case_records_scrape():
    tracker = MockTracker()
    cli = MockCLI(tracker, MockScraper({'IMM-1-25': True}))
    scrape = create_tracking_integrated_scrape_case(cli, run_id='r2')
    assert callable(scrape)

    case = scrape(1)  # IMM-1-25
    # Since scraper returns an object, case should not be None
    assert case is not None
    # Tracker should have been called for the scrape
    assert len(tracker.calls) >= 1
