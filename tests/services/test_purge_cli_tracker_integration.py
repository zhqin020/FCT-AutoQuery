import sys
import types
from unittest.mock import MagicMock

import pytest

# Provide a fake psycopg2 if it's not installed so we can import modules that
# reference it at top-level (the CLI imports case_tracking_service which
# imports psycopg2 at top-level).
if 'psycopg2' not in sys.modules:
    fake_extras = types.SimpleNamespace(RealDictCursor=object)
    sys.modules['psycopg2'] = types.SimpleNamespace(connect=lambda **kwargs: None, extras=fake_extras)

# Minimal `loguru` stub so `src.lib.logging_config` can import it during CLI init
if 'loguru' not in sys.modules:
    class DummyLogger:
        def debug(self, *a, **k):
            pass
        def info(self, *a, **k):
            pass
        def warning(self, *a, **k):
            pass
        def error(self, *a, **k):
            pass
    sys.modules['loguru'] = types.SimpleNamespace(logger=DummyLogger())

from src.cli.main import FederalCourtScraperCLI
import src.cli.purge as purge_mod


def test_cli_purge_invokes_tracker(monkeypatch, capsys):
    # Arrange: create a CLI instance
    cli = FederalCourtScraperCLI()

    # Replace purge_year function to avoid touching DB/files
    monkeypatch.setattr(purge_mod, "purge_year", lambda *args, **kwargs: {"audit_path": "tmp", "db": {}})

    # Replace CLI.tracker.purge_year with a MagicMock to assert it was called
    mock_tracker = MagicMock()
    mock_tracker.purge_year.return_value = {"cases_deleted": 1, "docket_entries_deleted": 1}
    cli.tracker = mock_tracker

    # Simulate CLI args: purge year 2021, yes to confirm, not dry-run
    monkeypatch.setenv("PYTHONUNBUFFERED", "1")
    monkeypatch.setattr(sys, "argv", ["prog", "purge", "2021", "--yes"])

    # Act: run the CLI; it should call purge_year (in purge_mod) and then tracker.purge_year
    # We avoid real DB calls by substituting purge_mod.purge_year.
    cli.run()

    # Assert: tracker.purge_year was invoked with 2021
    mock_tracker.purge_year.assert_called_once_with(2021)
