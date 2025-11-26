from src.cli.main import FederalCourtScraperCLI


class FakeScraper:
    def __init__(self):
        self._initialized = False

    def initialize_page(self):
        self._initialized = True

    def search_case(self, case_number):
        return True

    def scrape_case_data(self, case_number):
        # Return a minimal object with expected attributes
        obj = type("C", (), {})()
        obj.case_id = case_number
        obj.court_file_no = case_number
        return obj

    def close(self):
        pass


class FakeExporter:
    def __init__(self):
        self.export_called = False
        self.save_called = False

    def export_case_to_json(self, case):
        self.export_called = True
        return "/tmp/fake.json"

    def save_case_to_database(self, case):
        self.save_called = True
        return "success", None

    def case_exists(self, case_number):
        return False


def test_scrape_single_case_success(monkeypatch):
    cli = FederalCourtScraperCLI()
    fake_scraper = FakeScraper()
    cli.scraper = fake_scraper
    fake_exporter = FakeExporter()
    cli.exporter = fake_exporter

    case = cli.scrape_single_case("IMM-TEST-01")
    assert case is not None
    assert fake_exporter.export_called
    assert fake_exporter.save_called


def test_scrape_single_case_reuse_initialized(monkeypatch):
    cli = FederalCourtScraperCLI()
    fake_scraper = FakeScraper()
    # set initialized True to ensure initialize_page is not called
    fake_scraper._initialized = True
    cli.scraper = fake_scraper
    fake_exporter = FakeExporter()
    cli.exporter = fake_exporter

    case = cli.scrape_single_case("IMM-TEST-02")
    assert case is not None
    assert fake_exporter.export_called
