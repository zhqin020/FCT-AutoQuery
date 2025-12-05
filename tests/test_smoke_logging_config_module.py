from src.lib.logging_config import get_logger, setup_logging


def test_import_logging_config():
    assert get_logger is not None
    assert setup_logging is not None
