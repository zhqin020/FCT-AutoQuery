import time
from types import SimpleNamespace

import metrics_emitter
from metrics_emitter import MetricsEmitter, get_metric

from src.cli.main import FederalCourtScraperCLI
from src.lib.config import Config


class FakeExporter:
    def export_case_to_json(self, case):
        return "output/fake.json"

    def save_case_to_database(self, case):
        return True, "ok"

    def case_exists(self, case_number):
        return False


class FakeScraperSuccess:
    def __init__(self, headless=False):
        self._initialized = True

    def initialize_page(self):
        self._initialized = True

    def search_case(self, case_number):
        return True

    def scrape_case_data(self, case_number):
        return SimpleNamespace(case_id=case_number)

    def close(self):
        pass


class FakeScraperFail:
    def __init__(self, headless=False):
        self._initialized = True

    def initialize_page(self):
        self._initialized = True

    def search_case(self, case_number):
        return True

    def scrape_case_data(self, case_number):
        return None

    def close(self):
        pass


def reset_emitter():
    # Replace module-level default emitter with a fresh one
    metrics_emitter._default = MetricsEmitter()


def test_scrape_single_case_emits_success_metrics(monkeypatch):
    reset_emitter()
    cli = FederalCourtScraperCLI()
    # inject fake scraper and exporter
    cli.scraper = FakeScraperSuccess()
    cli.exporter = FakeExporter()

    # run
    res = cli.scrape_single_case("IMM-1-25")
    assert res is not None

    # metrics should include start, duration, retry_count
    assert get_metric("batch.job.start") is not None
    assert get_metric("batch.job.duration_seconds") is not None
    assert get_metric("batch.job.retry_count") == 1.0


def test_scrape_single_case_emits_failure_metrics(monkeypatch):
    reset_emitter()
    cli = FederalCourtScraperCLI()
    # inject failing scraper and exporter
    cli.scraper = FakeScraperFail()
    cli.exporter = FakeExporter()

    # ensure predictable retry count: monkeypatch Config.get_max_retries
    monkeypatch.setattr(Config, "get_max_retries", classmethod(lambda cls: 2))

    res = cli.scrape_single_case("IMM-2-25")
    assert res is None

    # metrics should include duration and retry_count == 2.0
    assert get_metric("batch.job.duration_seconds") is not None
    assert get_metric("batch.job.retry_count") == 2.0


def test_batch_run_emits_run_metrics(monkeypatch):
    reset_emitter()
    cli = FederalCourtScraperCLI()
    # discovery will produce a small list
    monkeypatch.setattr(cli.discovery, "generate_case_numbers_from_last", lambda year, max_cases: ["IMM-1-25", "IMM-2-25"]) 
    # inject exporter and scraper: first success, second fail
    class DualScraper:
        def __init__(self):
            self._initialized = True

        def initialize_page(self):
            self._initialized = True

        def search_case(self, case_number):
            return True

        def scrape_case_data(self, case_number):
            if case_number.endswith("1-25"):
                return SimpleNamespace(case_id=case_number)
            return None

        def close(self):
            pass

    cli.scraper = DualScraper()
    cli.exporter = FakeExporter()

    cases, skipped = cli.scrape_batch_cases(2025, max_cases=2)
    # one success, one failure
    assert len(cases) == 1

    # run-level metrics
    assert get_metric("batch.run.start") is not None
    assert get_metric("batch.run.duration_seconds") is not None
    # failure_rate should be 0.5 (1 failure / 2 processed)
    fr = get_metric("batch.run.failure_rate")
    assert fr == 0.5
