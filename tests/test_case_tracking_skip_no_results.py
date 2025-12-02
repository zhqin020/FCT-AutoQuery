from src.services.case_tracking_service import CaseTrackingService
from src.lib.config import Config


def test_should_skip_case_no_results_repeat(monkeypatch):
    service = CaseTrackingService()

    # Return an artificial status with repeated no_results
    monkeypatch.setattr(service, 'get_case_status', lambda x: {
        'last_outcome': 'no_results',
        'consecutive_no_results': 5,
        'last_processed_at': None,
    })

    # Set config safe threshold lower than consecutive_no_results
    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    assert 'no_results_repeated' in reason


def test_should_not_skip_case_no_results_under_threshold(monkeypatch):
    service = CaseTrackingService()

    monkeypatch.setattr(service, 'get_case_status', lambda x: {
        'last_outcome': 'no_results',
        'consecutive_no_results': 2,
        'last_processed_at': None,
    })

    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is False


def test_should_skip_when_history_shows_repeated_no_results(monkeypatch):
    service = CaseTrackingService()

    # Simulate no snapshot present
    monkeypatch.setattr(service, 'get_case_status', lambda x: None)
    # Force _count_recent_no_results to report repeated no_results
    monkeypatch.setattr(service, '_count_recent_no_results', lambda cn, limit: 3)
    monkeypatch.setattr(Config, 'get_safe_stop_no_records', classmethod(lambda cls: 3))

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    assert 'no_results_repeated' in reason
