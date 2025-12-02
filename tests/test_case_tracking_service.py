import pytest

from src.services.case_tracking_service import CaseTrackingService


def test_record_case_processing_creates_fallback_run(monkeypatch, caplog):
    service = CaseTrackingService()

    called = {"start_run": False}

    def fake_start_run(self, *args, **kwargs):
        called["start_run"] = True
        return "fallback_run_test_123"

    monkeypatch.setattr(CaseTrackingService, "start_run", fake_start_run, raising=True)

    # Monkeypatch psycopg2.connect to avoid needing a real DB
    def fake_connect(*args, **kwargs):
        class FakeConn:
            def cursor(self):
                class FakeCursor:
                    def execute(self, *a, **k):
                        pass

                    def fetchall(self):
                        return []

                    def fetchone(self):
                        return None

                    def close(self):
                        pass

                return FakeCursor()

            def commit(self):
                pass

            def close(self):
                pass

        return FakeConn()

    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "db")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setattr("psycopg2.connect", fake_connect, raising=False)

    # Should not raise even if run_id is None; the service creates a fallback
    service.record_case_processing(court_file_no="IMM-527-21", run_id=None, outcome="success")

    assert called["start_run"] is True
