import sys
from unittest.mock import MagicMock

from src.cli.main import FederalCourtScraperCLI
from src.lib.config import Config


def test_cli_probe_budget_default_uses_config(monkeypatch):
    cli = FederalCourtScraperCLI()

    captured = {}

    def fake_find_upper_bound(**kwargs):
        captured['probe_budget'] = kwargs.get('probe_budget')
        captured['safe_stop'] = kwargs.get('safe_stop')
        return (0, 0)

    monkeypatch.setattr('src.cli.main.BatchService.find_upper_bound', fake_find_upper_bound)

    sys_argv = sys.argv[:]
    try:
        sys.argv = ['prog', 'probe', '2025']
        cli.run()
    finally:
        sys.argv = sys_argv

    assert captured.get('probe_budget') == Config.get_probe_budget()
    assert captured.get('safe_stop') == Config.get_safe_stop_no_records()


def test_cli_probe_safe_stop_override(monkeypatch):
    cli = FederalCourtScraperCLI()

    captured = {}

    def fake_find_upper_bound(**kwargs):
        captured['safe_stop'] = kwargs.get('safe_stop')
        return (0, 0)

    monkeypatch.setattr('src.cli.main.BatchService.find_upper_bound', fake_find_upper_bound)

    sys_argv = sys.argv[:]
    try:
        sys.argv = ['prog', 'probe', '2025', '--safe-stop-no-records', '2']
        cli.run()
    finally:
        sys.argv = sys_argv

    assert captured.get('safe_stop') == 2
