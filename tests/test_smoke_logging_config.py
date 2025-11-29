def test_get_logger_returns_logger():
    from src.lib.logging_config import get_logger

    log = get_logger()
    # basic logger API assertions
    assert hasattr(log, "info")
    assert hasattr(log, "debug")
    assert callable(log.info)
