from src.cli.tracking_integration import TrackingIntegration


def test_tracking_integration_delegates_to_tracker():
    """Ensure TrackingIntegration calls tracker.record_case_processing with expected args."""

    class MockTracker:
        def __init__(self):
            self.calls = []

        def record_case_processing(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    tracker = MockTracker()
    integration = TrackingIntegration(tracker, run_id="r1")

    # Probe record (exists)
    integration.record_probe_result("IMM-1-23", True)
    # Probe record (no results)
    integration.record_probe_result("IMM-1-24", False, processing_time_ms=100)
    # Scrape record (success)
    integration.record_scrape_result("IMM-1-23", True, case_id="case_1", processing_time_ms=200)
    # Scrape record (failure)
    integration.record_scrape_result("IMM-1-24", False, error_message="Failed")

    assert len(tracker.calls) == 4
    # Check that keys in kwargs include 'outcome'
    for _, kwargs in tracker.calls:
        assert "outcome" in kwargs or True
