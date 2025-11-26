from unittest.mock import MagicMock


def test_cli_wiring_init():
    from src.cli.main import FederalCourtScraperCLI

    cli = FederalCourtScraperCLI()
    assert hasattr(cli, "scrape_single_case")
    assert hasattr(cli, "scrape_batch_cases")


def test_cli_single_calls_exporter(monkeypatch):
    from src.cli.main import FederalCourtScraperCLI

    cli = FederalCourtScraperCLI()

    # Mock exporter so we don't touch filesystem/DB
    mock_exporter = MagicMock()
    mock_exporter.export_case_to_json.return_value = (
        "output/json/2025/IMM-1-25-20251125.json"
    )
    mock_exporter.save_case_to_database.return_value = ("ok", "saved")
    cli.exporter = mock_exporter

    # Mock scraper to return a fake Case
    mock_scraper = MagicMock()
    mock_scraper.initialize_page.return_value = None
    mock_scraper.search_case.return_value = True
    fake_case = MagicMock()
    fake_case.case_id = "IMM-1-25"
    mock_scraper.scrape_case_data.return_value = fake_case
    cli.scraper = mock_scraper

    result = cli.scrape_single_case("IMM-1-25")
    assert result is not None
    mock_exporter.export_case_to_json.assert_called_once_with(fake_case)
