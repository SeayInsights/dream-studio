"""Common utilities for scripts

Provides path management and database utilities for scripts running from repo root.
Scripts can import from this module without sys.path manipulation.

Usage:
    from common import get_db_path, get_runtime_dir, get_audit_report_path

    db_path = get_db_path()
    report_path = get_audit_report_path("my_report.md")
"""

from pathlib import Path
from datetime import date

from core.config.paths import state_dir, user_data_dir, audit_dir, logs_dir


def get_db_path() -> str:
    return str(state_dir() / "studio.db")


def get_runtime_dir() -> Path:
    return user_data_dir()


def get_audit_report_path(filename: str) -> Path:
    path = audit_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / filename


def get_log_path(filename: str) -> Path:
    path = logs_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / filename


def get_timestamped_audit_report(prefix: str, extension: str = "md") -> Path:
    path = audit_dir()
    path.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    return path / f"{prefix}_{today}.{extension}"
