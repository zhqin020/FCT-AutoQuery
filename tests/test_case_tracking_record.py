import time
from src.services.case_tracking_service import CaseTrackingService


def test_record_case_processing_persists_and_is_visible():
    svc = CaseTrackingService()
    test_case = f"IMM-TEST-{int(time.time()) % 100000}"
    run_id = f"unittest_{int(time.time())}" 

    # Purge pre-existing data for test case if any
    try:
        svc.purge_case_number(test_case)
    except Exception:
        pass

    # Record an entry programmatically
    svc.record_case_processing(test_case, run_id, 'no_data', reason='unit test', message='ensure persistence')

    # Query the history and status via the service API
    history = svc.get_case_history(test_case, limit=5)
    assert isinstance(history, list)
    assert len(history) >= 1
    assert history[0]['run_id'] == run_id
    assert history[0]['outcome'] in ('no_data', 'no-results', 'no_results')

    status = svc.get_case_status(test_case)
    assert status is not None
    assert status.get('last_run_id') == run_id
    # Clean up test data
    try:
        svc.purge_case_number(test_case)
    except Exception:
        pass


def test_outcome_normalization_for_no_results():
    svc = CaseTrackingService()
    test_case = f"IMM-NORM-{int(time.time()) % 100000}"
    run_id = f"unittest_{int(time.time())}"
    svc.purge_case_number(test_case)
    svc.record_case_processing(test_case, run_id, 'no-results', reason='normalization test', message='test normalize')
    history = svc.get_case_history(test_case, limit=5)
    assert len(history) >= 1
    assert history[0]['outcome'] == 'no_data'
    # Cleanup
    try:
        svc.purge_case_number(test_case)
    except Exception:
        pass


def test_snapshot_update_failure_does_not_rollback_history(monkeypatch):
    svc = CaseTrackingService()
    test_case = f"IMM-FALSE-{int(time.time()) % 100000}"
    run_id = f"unittest_{int(time.time())}"
    svc.purge_case_number(test_case)

    # Monkeypatch the snapshot update to raise an exception
    monkeypatch.setattr(svc, '_update_snapshot', lambda *args, **kwargs: (_ for _ in ()).throw(Exception('simulated snapshot failure')))

    # Record should still persist history even if snapshot update fails
    svc.record_case_processing(test_case, run_id, 'no_data', reason='simulate snapshot fail', message='snapfail')
    history = svc.get_case_history(test_case, limit=5)
    assert len(history) >= 1
    assert history[0]['run_id'] == run_id
    # Cleanup
    try:
        svc.purge_case_number(test_case)
    except Exception:
        pass


def test_record_case_processing_dedupes_duplicate_outcome():
    svc = CaseTrackingService()
    test_case = f"IMM-DEDUPE-{int(time.time()) % 100000}"
    run_id1 = f"unittest_{int(time.time())}_1"
    run_id2 = f"unittest_{int(time.time())}_2"
    svc.purge_case_number(test_case)

    svc.record_case_processing(test_case, run_id1, 'no_data', reason='first')
    svc.record_case_processing(test_case, run_id2, 'no_data', reason='second')

    history = svc.get_case_history(test_case, limit=10)
    # There should only be one history record if duplicate outcomes are de-duplicated
    assert len(history) == 1
    assert history[0]['outcome'] == 'no_data'

    # Cleanup
    try:
        svc.purge_case_number(test_case)
    except Exception:
        pass


def test_no_data_resets_retry_count():
    svc = __import__('src.services.simplified_tracking_service', fromlist=['']).SimplifiedTrackingService()
    CaseStatus = __import__('src.services.simplified_tracking_service', fromlist=['']).CaseStatus
    test_case = f"IMM-RESET-{int(time.time()) % 100000}"

    # Ensure the case is absent first
    try:
        import psycopg2
        conn = psycopg2.connect(**svc.db_config)
        cur = conn.cursor()
        cur.execute("DELETE FROM cases WHERE case_number = %s", (test_case,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass

    run_id = f"unittest_{int(time.time())}"
    # Record two failed attempts
    svc.mark_case_attempt(test_case, CaseStatus.FAILED, "fail1")
    svc.mark_case_attempt(test_case, CaseStatus.FAILED, "fail2")

    info = svc.get_case_info(test_case)
    assert info is not None
    assert info.get('retry_count', 0) >= 2

    # Now mark as no_data and ensure retry_count resets to 0
    svc.mark_case_attempt(test_case, CaseStatus.NO_DATA)
    info = svc.get_case_info(test_case)
    assert info is not None
    assert info.get('status') == CaseStatus.NO_DATA
    assert info.get('retry_count', 0) == 0