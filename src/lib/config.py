"""Configuration management for Federal Court scraper.

This module loads configuration from TOML files if present:
- `config.private.toml` (local, not checked into VCS)
- `config.toml` (project-level)

Values are read from the loaded config first, then fall back to
environment variables (optional), then to built-in defaults.
"""

import os
from typing import Optional
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover - fallback for older envs
    tomllib = None

# Default values
DEFAULT_RATE_LIMIT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 30

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_JSON_FILENAME = "cases.json"
DEFAULT_EXPORT_JSON_ONLY = True

DEFAULT_HEADLESS = True
DEFAULT_BROWSER = "chrome"

DEFAULT_PER_CASE_SUBDIR = "json"
DEFAULT_EXPORT_WRITE_RETRIES = 2
DEFAULT_EXPORT_WRITE_BACKOFF_SECONDS = 1
DEFAULT_MAX_DRIVER_RESTARTS = 1

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "logs/scraper.log"

DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = 5432
DEFAULT_DB_NAME = "fct_db"
DEFAULT_DB_USER = "fct_user"
DEFAULT_DB_PASSWORD = "fctpass"

DEFAULT_SAVE_MODAL_HTML = False
DEFAULT_ENABLE_RUN_LOGGER = True
DEFAULT_WRITE_AUDIT = False
DEFAULT_DOCKET_PARSE_MAX_ERRORS = 3
DEFAULT_SAFE_STOP_NO_RECORDS = 500
DEFAULT_PERSIST_RAW_HTML = False
DEFAULT_PROBE_BUDGET = 200
DEFAULT_BACKOFF_FACTOR = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 60.0


def _load_toml_config() -> dict:
    """Load config from `config.private.toml` then `config.toml` if available.

    Returns a dict with merged values (private overrides project file).
    """
    cfg: dict = {}
    if tomllib is None:
        return cfg

    cwd = Path.cwd()
    for fname in ("config.private.toml", "config.toml"):
        p = cwd / fname
        if p.exists():
            try:
                with open(p, "rb") as f:
                    data = tomllib.load(f)
                    if isinstance(data, dict):
                        # shallow merge
                        for k, v in data.items():
                            if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                                cfg[k].update(v)
                            else:
                                cfg[k] = v
            except Exception:
                # Ignore parse errors and continue
                continue
    return cfg


_CONFIG = _load_toml_config()


def _get_from_config(section: str, key: str):
    try:
        return _CONFIG.get(section, {}).get(key)
    except Exception:
        return None


class Config:
    """Configuration accessors.

    Methods mirror the previous API but prefer values from TOML files.
    """

    @classmethod
    def get_rate_limit_seconds(cls) -> float:
        return float(
            _get_from_config("app", "rate_limit_seconds")
            or os.getenv("FCT_RATE_LIMIT_SECONDS")
            or DEFAULT_RATE_LIMIT_SECONDS
        )

    @classmethod
    def get_max_retries(cls) -> int:
        return int(
            _get_from_config("app", "max_retries")
            or os.getenv("FCT_MAX_RETRIES")
            or DEFAULT_MAX_RETRIES
        )

    @classmethod
    def get_timeout_seconds(cls) -> int:
        return int(
            _get_from_config("app", "timeout_seconds")
            or os.getenv("FCT_TIMEOUT_SECONDS")
            or DEFAULT_TIMEOUT_SECONDS
        )

    @classmethod
    def get_output_dir(cls) -> str:
        return (
            _get_from_config("app", "output_dir")
            or os.getenv("FCT_OUTPUT_DIR")
            or DEFAULT_OUTPUT_DIR
        )

    @classmethod
    def get_per_case_subdir(cls) -> str:
        return (
            _get_from_config("app", "per_case_subdir")
            or os.getenv("FCT_PER_CASE_SUBDIR")
            or DEFAULT_PER_CASE_SUBDIR
        )

    @classmethod
    def get_export_write_retries(cls) -> int:
        return int(
            _get_from_config("app", "export_write_retries")
            or os.getenv("FCT_EXPORT_WRITE_RETRIES")
            or DEFAULT_EXPORT_WRITE_RETRIES
        )

    @classmethod
    def get_export_write_backoff_seconds(cls) -> int:
        return int(
            _get_from_config("app", "export_write_backoff_seconds")
            or os.getenv("FCT_EXPORT_WRITE_BACKOFF_SECONDS")
            or DEFAULT_EXPORT_WRITE_BACKOFF_SECONDS
        )

    @classmethod
    def get_max_driver_restarts(cls) -> int:
        return int(
            _get_from_config("app", "max_driver_restarts")
            or os.getenv("FCT_MAX_DRIVER_RESTARTS")
            or DEFAULT_MAX_DRIVER_RESTARTS
        )

    @classmethod
    def get_docket_parse_max_errors(cls) -> int:
        return int(
            _get_from_config("app", "docket_parse_max_errors")
            or os.getenv("FCT_DOCKET_PARSE_MAX_ERRORS")
            or DEFAULT_DOCKET_PARSE_MAX_ERRORS
        )

    @classmethod
    def get_csv_filename(cls) -> str:
        raise AttributeError("CSV filename support removed; use JSON exports only")

    @classmethod
    def get_json_filename(cls) -> str:
        return (
            _get_from_config("app", "json_filename")
            or os.getenv("FCT_JSON_FILENAME")
            or DEFAULT_JSON_FILENAME
        )

    @classmethod
    def get_export_json_only(cls) -> bool:
        val = _get_from_config("app", "export_json_only")
        if val is None:
            val = os.getenv("FCT_EXPORT_JSON_ONLY")
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val) if val is not None else DEFAULT_EXPORT_JSON_ONLY

    @classmethod
    def get_headless(cls) -> bool:
        val = _get_from_config("app", "headless")
        if val is None:
            val = os.getenv("FCT_HEADLESS")
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val) if val is not None else DEFAULT_HEADLESS

    @classmethod
    def get_browser(cls) -> str:
        return (
            _get_from_config("app", "browser")
            or os.getenv("FCT_BROWSER")
            or DEFAULT_BROWSER
        )

    @classmethod
    def get_log_level(cls) -> str:
        return (
            _get_from_config("app", "log_level")
            or os.getenv("FCT_LOG_LEVEL")
            or DEFAULT_LOG_LEVEL
        )

    @classmethod
    def get_log_file(cls) -> Optional[str]:
        return (
            _get_from_config("app", "log_file")
            or os.getenv("FCT_LOG_FILE")
            or DEFAULT_LOG_FILE
        )

    @classmethod
    def get_output_path(cls, filename: str) -> Path:
        output_dir = Path(cls.get_output_dir())
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / filename

    @classmethod
    def get_save_modal_html(cls) -> bool:
        val = _get_from_config("app", "save_modal_html")
        if val is None:
            val = os.getenv("FCT_SAVE_MODAL_HTML")
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val) if val is not None else DEFAULT_SAVE_MODAL_HTML

    @classmethod
    def get_safe_stop_no_records(cls) -> int:
        return int(
            _get_from_config("app", "safe_stop_no_records")
            or os.getenv("FCT_SAFE_STOP_NO_RECORDS")
            or DEFAULT_SAFE_STOP_NO_RECORDS
        )

    @classmethod
    def get_persist_raw_html(cls) -> bool:
        val = _get_from_config("app", "persist_raw_html")
        if val is None:
            val = os.getenv("FCT_PERSIST_RAW_HTML")
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val) if val is not None else DEFAULT_PERSIST_RAW_HTML

    @classmethod
    def get_probe_budget(cls) -> int:
        return int(
            _get_from_config("app", "probe_budget")
            or os.getenv("FCT_PROBE_BUDGET")
            or DEFAULT_PROBE_BUDGET
        )

    @classmethod
    def get_backoff_factor(cls) -> float:
        return float(
            _get_from_config("app", "backoff_factor")
            or os.getenv("FCT_BACKOFF_FACTOR")
            or DEFAULT_BACKOFF_FACTOR
        )

    @classmethod
    def get_max_backoff_seconds(cls) -> float:
        return float(
            _get_from_config("app", "max_backoff_seconds")
            or os.getenv("FCT_MAX_BACKOFF_SECONDS")
            or DEFAULT_MAX_BACKOFF_SECONDS
        )

    @classmethod
    def get_enable_run_logger(cls) -> bool:
        val = _get_from_config("app", "enable_run_logger")
        if val is None:
            val = os.getenv("FCT_ENABLE_RUN_LOGGER")
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val) if val is not None else DEFAULT_ENABLE_RUN_LOGGER

    @classmethod
    def get_write_audit(cls) -> bool:
        val = _get_from_config("app", "write_audit")
        if val is None:
            val = os.getenv("FCT_WRITE_AUDIT")
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val) if val is not None else DEFAULT_WRITE_AUDIT

    @classmethod
    def get_csv_path(cls) -> Path:
        raise AttributeError("CSV path support removed; use JSON exports only")

    @classmethod
    def get_db_host(cls) -> str:
        return (
            _get_from_config("database", "host")
            or os.getenv("DB_HOST")
            or DEFAULT_DB_HOST
        )

    @classmethod
    def get_db_port(cls) -> int:
        return int(
            _get_from_config("database", "port")
            or os.getenv("DB_PORT")
            or DEFAULT_DB_PORT
        )

    @classmethod
    def get_db_name(cls) -> str:
        return (
            _get_from_config("database", "name")
            or os.getenv("DB_NAME")
            or DEFAULT_DB_NAME
        )

    @classmethod
    def get_db_user(cls) -> str:
        return (
            _get_from_config("database", "user")
            or os.getenv("DB_USER")
            or DEFAULT_DB_USER
        )

    @classmethod
    def get_db_password(cls) -> str:
        return (
            _get_from_config("database", "password")
            or os.getenv("DB_PASSWORD")
            or DEFAULT_DB_PASSWORD
        )

    @classmethod
    def get_db_config(cls) -> dict:
        return {
            "host": cls.get_db_host(),
            "port": cls.get_db_port(),
            "database": cls.get_db_name(),
            "user": cls.get_db_user(),
            "password": cls.get_db_password(),
        }
