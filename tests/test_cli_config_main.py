import pytest
from src.lib.config import Config


def test_default_enable_run_logger_is_false():
    assert Config.get_enable_run_logger() is False


def test_db_config_has_required_keys():
    db_cfg = Config.get_db_config()
    assert 'host' in db_cfg and 'database' in db_cfg and 'user' in db_cfg and 'password' in db_cfg
