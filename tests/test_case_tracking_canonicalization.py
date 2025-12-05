import psycopg2
from src.services.case_tracking_service import CaseTrackingService


class FakeCursor:
    def __init__(self, match_value):
        self.match_value = match_value
        self.last_params = None
        self.last_query = None

    def execute(self, query, params=None):
        self.last_params = params
        self.last_query = query

    def fetchone(self):
        if self.last_params:
            import re
            # If the query appears to use a regex (~* operator), evaluate the pattern
            if self.last_query and '~*' in str(self.last_query):
                try:
                    pattern = self.last_params[0]
                    if re.search(pattern, self.match_value, flags=re.IGNORECASE):
                        return (1,)
                except Exception:
                    pass
            else:
                if self.last_params[0] == self.match_value:
                    return (1,)
        return None

    def close(self):
        return


class FakeConn:
    def __init__(self, match_value):
        self._c = FakeCursor(match_value)

    def cursor(self):
        return self._c

    def close(self):
        return


def test_should_skip_when_db_has_padded_variant(monkeypatch):
    """If DB contains padded case 'IMM-0005-21', calling should_skip_case('IMM-5-21') should return True."""
    service = CaseTrackingService()

    # Make psycopg2.connect return a connection that reports a padded variant existing
    def fake_connect(**kwargs):
        return FakeConn('IMM-0005-21')

    monkeypatch.setattr(psycopg2, 'connect', fake_connect)

    should_skip, reason = service.should_skip_case('IMM-5-21')
    assert should_skip is True
    assert reason == 'exists_in_db'


def test_should_skip_when_db_has_canonical_variant(monkeypatch):
    """If DB contains canonical case 'IMM-5-21', calling should_skip_case('IMM-0005-21') should return True."""
    service = CaseTrackingService()

    def fake_connect2(**kwargs):
        return FakeConn('IMM-5-21')

    monkeypatch.setattr(psycopg2, 'connect', fake_connect2)

    should_skip, reason = service.should_skip_case('IMM-0005-21')
    assert should_skip is True
    assert reason == 'exists_in_db'
