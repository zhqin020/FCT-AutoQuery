from src.lib.config import Config
from src.services.url_discovery_service import UrlDiscoveryService


def test_generate_case_numbers_for_year_no_padding():
    svc = UrlDiscoveryService(Config)
    cases = svc.generate_case_numbers_for_year(2025, start_num=1, max_cases=3)
    assert cases == ["IMM-1-25", "IMM-2-25", "IMM-3-25"]


def test_generate_case_numbers_from_last_resumes_correctly(monkeypatch):
    # monkeypatch the DB-backed get_last_processed_case to return a sample last case
    svc = UrlDiscoveryService(Config)

    def fake_last(year):
        return "IMM-4-25"

    monkeypatch.setattr(
        UrlDiscoveryService, "get_last_processed_case", lambda self, y: fake_last(y)
    )

    cases = svc.generate_case_numbers_from_last(2025, max_cases=3)
    # last was 4 -> should start from 5
    assert cases[0] == "IMM-5-25"
    assert cases[:3] == ["IMM-5-25", "IMM-6-25", "IMM-7-25"]
    cases = svc.generate_case_numbers_from_last(2025, max_cases=3)
