import sys
from types import SimpleNamespace

import pytest


def run_main_with_argv(monkeypatch, argv):
    # Import inside helper to ensure monkeypatching takes effect
    from src.cli import main as cli_main

    monkeypatch.setattr(sys, "argv", argv)
    # Run main and capture SystemExit if raised
    try:
        cli_main.main()
    except SystemExit as e:
        # Allow SystemExit from argparse or explicit exits
        if e.code not in (0, None):
            raise


def test_probe_dry_run_does_not_instantiate_scraper(monkeypatch, capsys):
    # Make CaseScraperService raise if instantiated
    import src.cli.main as cli_module

    def bad_constructor(*args, **kwargs):
        raise RuntimeError("Scraper should not be instantiated in dry-run")

    monkeypatch.setattr(cli_module, "CaseScraperService", bad_constructor)

    run_main_with_argv(monkeypatch, ["prog", "probe", "2025"])

    out = capsys.readouterr().out
    assert "[dry-run] would check ID" in out


def test_probe_live_uses_scraper(monkeypatch, capsys):
    # Provide a mocked CaseScraperService that responds True up to 123
    class MockScraper:
        def __init__(self, *args, **kwargs):
            self._initialized = False

        def initialize_page(self):
            self._initialized = True

        def search_case(self, case_number: str) -> bool:
            # expect format IMM-<n>-<yy>
            try:
                parts = case_number.split("-")
                n = int(parts[1])
            except Exception:
                return False
            return n <= 123

    import src.cli.main as cli_module
    monkeypatch.setattr(cli_module, "CaseScraperService", MockScraper)

    # Use small initial_high and a reasonable budget to keep test fast
    run_main_with_argv(monkeypatch, [
        "prog",
        "probe",
        "2025",
        "--live",
        "--initial-high",
        "50",
        "--probe-budget",
        "200",
    ])

    out = capsys.readouterr().out
    assert "Probe result:" in out
    assert "Approx upper numeric id:" in out
    assert "Probes used:" in out
