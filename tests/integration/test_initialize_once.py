from src.cli.main import FederalCourtScraperCLI


def test_initialize_page_called_once_per_batch(monkeypatch, tmp_path):
    cli = FederalCourtScraperCLI()

    calls = {"init": 0}

    def fake_initialize(self):
        calls["init"] += 1
        # mimic successful initialization
        setattr(self, "_initialized", True)

    # Replace the real initialize_page with our counter
    monkeypatch.setattr(
        "src.services.case_scraper_service.CaseScraperService.initialize_page",
        fake_initialize,
    )

    # Make search_case always succeed
    monkeypatch.setattr(
        "src.services.case_scraper_service.CaseScraperService.search_case",
        lambda self, cn: True,
    )

    # Make scrape_case_data return a minimal object with attributes used by CLI
    class FakeCase:
        def __init__(self, cid):
            self.case_id = cid
            self.court_file_no = cid

    monkeypatch.setattr(
        "src.services.case_scraper_service.CaseScraperService.scrape_case_data",
        lambda self, cn: FakeCase(cn),
    )

    # Provide a fake exporter to avoid DB/filesystem side-effects
    class FakeExporter:
        def case_exists(self, cn):
            return False

        def export_case_to_json(self, case):
            return str(tmp_path / f"{case.case_id}.json")

        def save_case_to_database(self, case):
            return "success", None

    cli.exporter = FakeExporter()

    # Make discovery return a small list of case numbers
    monkeypatch.setattr(
        "src.services.url_discovery_service.UrlDiscoveryService.generate_case_numbers_from_last",
        lambda self, year, max_cases: ["IMM-1-25", "IMM-2-25", "IMM-3-25"],
    )

    # Run the batch scrape
    cases, skipped = cli.scrape_batch_cases(2025, max_cases=3)

    # Expect initialize_page called exactly once
    assert calls["init"] == 1
    # All three cases should have been scraped
    assert len(cases) == 3
