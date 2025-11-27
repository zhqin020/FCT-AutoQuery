import os
from src.lib.config import Config


def test_default_docket_parse_max_errors():
    # Ensure default value is returned when env/config not set
    if "FCT_DOCKET_PARSE_MAX_ERRORS" in os.environ:
        del os.environ["FCT_DOCKET_PARSE_MAX_ERRORS"]
    assert isinstance(Config.get_docket_parse_max_errors(), int)
    assert Config.get_docket_parse_max_errors() == 3


def test_env_overrides_docket_parse_max_errors(monkeypatch):
    monkeypatch.setenv("FCT_DOCKET_PARSE_MAX_ERRORS", "7")
    assert Config.get_docket_parse_max_errors() == 7
