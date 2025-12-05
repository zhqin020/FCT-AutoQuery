from src.lib.logging_config import get_logger

def test_logging_config_importable():
    assert get_logger is not None
import os
from src.lib.logging_config import setup_logging, get_logger


def test_setup_logging_creates_file(tmp_path, caplog):
    log_file = tmp_path / "testlog.log"
    setup_logging(log_level="DEBUG", log_file=str(log_file))
    logger = get_logger()
    logger.debug("test debug")
    # The file is named with a numbered suffix by default (base-1.log). Check that.
    numbered_log = log_file.parent / (log_file.stem + "-1" + log_file.suffix)
    assert numbered_log.exists()
    content = numbered_log.read_text()
    assert "test debug" in content
