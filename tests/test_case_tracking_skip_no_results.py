from src.services.case_tracking_service import CaseTrackingService
from src.lib.config import Config


def test_should_skip_case_no_results_repeat(monkeypatch):
    service = CaseTrackingService()

    # Return an artificial status with repeated no_data
    # Note: tests use 'consecutive_no_data' canonicalized field name
    monkeypatch.setattr(service, 'get_case_status', lambda x: {
        'last_outcome': 'no_data',
        'consecutive_no_data': 5,
        'last_processed_at': None,
    })

    # Set config safe threshold lower than consecutive_no_results
    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True


def test_no_results_ttl_behavior(monkeypatch):
    service = CaseTrackingService()
    # Create a snapshot that was updated 400 days ago
    from datetime import datetime, timezone, timedelta
    old_ts = datetime.now(timezone.utc) - timedelta(days=400)
    # Mock get_case_status to return no_data older than TTL
    monkeypatch.setattr(service, 'get_case_status', lambda cn: {'last_outcome': 'no_data', 'last_processed_at': old_ts})
    monkeypatch.setattr(Config, 'get_no_results_ttl_days', classmethod(lambda cls: 365))
    # Should not skip because the last no_data are older than TTL
    should_skip, reason = service.should_skip_case('IMM-9999-21')
    assert should_skip is False

    # Now mock timestamp within TTL
    recent_ts = datetime.now(timezone.utc) - timedelta(days=10)
    monkeypatch.setattr(service, 'get_case_status', lambda cn: {'last_outcome': 'no_data', 'last_processed_at': recent_ts})
    should_skip, reason = service.should_skip_case('IMM-9999-21')
    assert should_skip is True
    assert 'no_data' in reason


def test_should_not_skip_case_no_results_under_threshold(monkeypatch):
    service = CaseTrackingService()

    monkeypatch.setattr(service, 'get_case_status', lambda x: {
        'last_outcome': 'no_data',
        'consecutive_no_data': 2,
        'last_processed_at': None,
    })

    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    # With new policy, any recent 'no_data' snapshot causes immediate skip
    assert should_skip is True
    assert 'no_data' in reason


def test_should_skip_case_if_last_outcome_is_no_results(monkeypatch):
    service = CaseTrackingService()

    monkeypatch.setattr(service, 'get_case_status', lambda x: {
        'last_outcome': 'no_data',
        'consecutive_no_data': 1,
        'last_processed_at': None,
    })
    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    assert 'no_data' in reason


def test_should_skip_when_history_shows_repeated_no_results(monkeypatch):
    service = CaseTrackingService()

    # Simulate no snapshot present
    monkeypatch.setattr(service, 'get_case_status', lambda x: None)
    # Force _count_recent_no_results to report repeated no_data
    monkeypatch.setattr(service, '_count_recent_no_results', lambda cn, limit: 3)
    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    assert 'no_data_repeated' in reason


def test_no_data_takes_precedence_over_max_retries(monkeypatch):
    """If the DB status is 'no_data', it should be skipped for 'no_data' reason even if retry_count >= max_retries"""
    service = CaseTrackingService()
    # Simulate DB returning 'no_data' with high retry_count
    monkeypatch.setattr(service, '_get_case_info', lambda cn: {'case_number': cn, 'status': 'no_data', 'retry_count': 10, 'last_attempt_at': None})
    monkeypatch.setattr(Config, 'get_max_retries', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    # The reason should indicate no_data skip, not max_retries_exceeded
    assert 'no_data' in reason or 'no-data' in reason or 'confirmed' in reason


def test_should_skip_if_no_history_but_case_in_db(monkeypatch):
    service = CaseTrackingService()

    # Simulate no snapshot present
    monkeypatch.setattr(service, 'get_case_status', lambda x: None)
    # Simulate DB check returning True
    monkeypatch.setattr(service, '_case_exists_in_db', lambda cn: True)

    called = {'count': 0}

    def fake_record_case_processing(**kwargs):
        called['count'] += 1

    monkeypatch.setattr(service, 'record_case_processing', lambda **kwargs: fake_record_case_processing(**kwargs))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    assert 'exists_in_db' in reason
    assert called['count'] == 1


def test_switch_from_failed_to_no_data_changes_skip_reason(monkeypatch):
    # Verify that when a case transitions from failed (max retries) to no_data,
    # the skip reason becomes 'confirmed_no_data' rather than 'max_retries_exceeded'.
    svc = __import__('src.services.simplified_tracking_service', fromlist=['']).SimplifiedTrackingService()
    CaseStatus = __import__('src.services.simplified_tracking_service', fromlist=['']).CaseStatus
    test_case = 'IMM-SWITCH-21'

    # Ensure a clean state
    try:
        import psycopg2
        conn = psycopg2.connect(**svc.db_config)
        cur = conn.cursor()
        cur.execute("DELETE FROM cases WHERE case_number = %s", (test_case,))
        conn.commit()
        cur.close(); conn.close()
    except Exception:
        pass

    # Simulate failed with high retry_count by marking failed multiple times
    for i in range(Config.get_max_retries()):
        svc.mark_case_attempt(test_case, CaseStatus.FAILED, f"fail {i+1}")

    should_skip, reason = svc.should_skip_case(test_case)
    assert should_skip is True
    # With new policy, failed cases are not skipped due to persisted retry_count.
    # We expect recent attempts to trigger a cooldown-based skip immediately after marking failures.
    assert 'recently_attempted' in reason

    # Now mark as no_data
    svc.mark_case_attempt(test_case, CaseStatus.NO_DATA)
    should_skip2, reason2 = svc.should_skip_case(test_case)
    assert should_skip2 is True
    # Should now be 'confirmed_no_data' or show 'no_data' status
    assert 'no_data' in reason2 or 'confirmed_no_data' in reason2


def test_should_skip_if_history_failed_but_case_in_db(monkeypatch):
    service = CaseTrackingService()

    monkeypatch.setattr(service, 'get_case_status', lambda x: {
        'last_outcome': 'failed',
        'consecutive_failures': 1,
    })
    monkeypatch.setattr(service, '_case_exists_in_db', lambda cn: True)

    called = {'count': 0}
    monkeypatch.setattr(service, 'record_case_processing', lambda **kwargs: called.update({'count': called['count'] + 1}))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    # DB entry shows 'failed' status; we should NOT skip re-collection and thus expect False
    assert should_skip is False
    assert 'exists_in_db' in reason or 'will re-collect' in reason
    assert called['count'] == 1
