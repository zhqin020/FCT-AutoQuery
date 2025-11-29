"""Logging configuration for Federal Court scraper."""

from loguru import logger
import sys
from pathlib import Path
from typing import Optional, Any
import shutil
import os


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_base: Optional[str] = None,
    max_index: Optional[int] = None,
) -> None:
    """Setup logging configuration for the scraper.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    # Remove default handler
    logger.remove()

    # Console handler with color
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_dir = log_path.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        # Determine rotation base name and max index (configurable via args or env vars)
        base = log_base or os.getenv("LOG_BASE_NAME") or log_path.stem
        ext = log_path.suffix or ".log"
        try:
            max_idx = int(max_index or os.getenv("LOG_MAX_INDEX") or 9)
        except Exception:
            max_idx = 9

        def rotate_numbered_logs(directory: Path, base_name: str, extension: str, max_index: int = 9) -> Path:
            """Rotate existing numbered logs and return the path for the new log (base-1.ext).

            This shifts base-(i-1).ext -> base-i.ext for i from max_index down to 2,
            then ensures base-1.ext is available for the new log file.
            """
            # Move from highest to lowest to avoid clobbering
            for i in range(max_index, 1, -1):
                src = directory / f"{base_name}-{i-1}{extension}"
                dst = directory / f"{base_name}-{i}{extension}"
                if src.exists():
                    try:
                        if dst.exists():
                            dst.unlink()
                        src.replace(dst)
                    except Exception:
                        # Best-effort: try shutil.move as fallback
                        try:
                            shutil.move(str(src), str(dst))
                        except Exception:
                            pass

            # New log is base-1.ext
            new_log = directory / f"{base_name}-1{extension}"
            # If an old base-1 exists unexpectedly, remove it (we've moved it to -2 above)
            if new_log.exists():
                try:
                    new_log.unlink()
                except Exception:
                    pass
            return new_log

        numbered_log = rotate_numbered_logs(log_dir, base, ext, max_idx)

        logger.add(
            numbered_log,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            encoding="utf-8",
        )

    logger.info("Logging initialized with level: {}", log_level)


def get_logger() -> Any:
    """Get the configured logger instance.

    Returns:
        Logger: Configured loguru logger
    """
    return logger


# Initialize with default settings
setup_logging()
