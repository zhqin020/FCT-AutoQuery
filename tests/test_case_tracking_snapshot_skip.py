from src.services.case_tracking_service import CaseTrackingService
from src.lib.config import Config


def test_record_case_processing_marks_snapshot_and_should_skip(monkeypatch):
    service = CaseTrackingService()

    # Use a unique case id to avoid interfering with existing tests
    case_id = 'IMM-9999-99'

    # Record a no_data outcome to DB via the service
    run_id = service.start_run(processing_mode='test')
    service.record_case_processing(court_file_no=case_id, run_id=run_id, outcome='no_data')

    # Now should_skip_case should return True due to snapshot
    should_skip, reason = service.should_skip_case(case_id)
    assert should_skip is True
    assert 'no_data' in reason
