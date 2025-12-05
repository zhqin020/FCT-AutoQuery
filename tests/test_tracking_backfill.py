from src.services.case_tracking_service import CaseTrackingService


def test_backfill_missing_snapshots(monkeypatch):
    svc = CaseTrackingService()

    # Return two cases in DB for year
    monkeypatch.setattr(svc, 'get_cases_in_db_for_year', lambda year, limit=None, since_days=None: ['IMM-100-21', 'IMM-101-21'])

    # Simulate snapshot missing for both by returning None
    monkeypatch.setattr(svc, 'get_case_status', lambda cn: None)

    recorded = []
    def fake_record(court_file_no, run_id, outcome, reason=None, processing_mode=None, **kwargs):
        recorded.append((court_file_no, outcome, reason))

    monkeypatch.setattr(svc, 'record_case_processing', fake_record)

    created = svc.backfill_missing_snapshots_from_cases(2021, limit=10)

    assert created == 2
    assert ('IMM-100-21', 'skipped', 'exists_in_db') in recorded
    assert ('IMM-101-21', 'skipped', 'exists_in_db') in recorded
