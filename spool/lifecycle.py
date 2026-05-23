"""Spool archive lifecycle operations — weekly archiving and yearly consolidation."""

from __future__ import annotations

import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from spool.config import get_spool_root


def _archives_dir(root: Path) -> Path:
    return root / "archives"


def _processed_dir(root: Path) -> Path:
    return root / "processed"


def archive_week(root: Path | None = None, today: date | None = None) -> dict[str, Any]:
    """Bundle prior-week processed files into a dated zip.

    Returns a dict with keys:
        ok             bool   — True on success or nothing-to-do
        archive_name   str    — name of the zip created (or None)
        files_archived int    — number of files bundled
        skipped_reason str    — human-readable reason when skipped (or None)
        error          str    — error message on failure (or None)
    """
    if root is None:
        root = get_spool_root()
    if today is None:
        today = date.today()

    processed = _processed_dir(root)
    if not processed.exists():
        return {
            "ok": True,
            "archive_name": None,
            "files_archived": 0,
            "skipped_reason": "processed/ directory does not exist",
            "error": None,
        }

    # Collect files whose mtime is before the start of the current week (Monday)
    week_start = today - timedelta(days=today.weekday())
    candidates = [
        f for f in processed.iterdir()
        if f.is_file() and date.fromtimestamp(f.stat().st_mtime) < week_start
    ]

    if not candidates:
        return {
            "ok": True,
            "archive_name": None,
            "files_archived": 0,
            "skipped_reason": "no prior-week files to archive",
            "error": None,
        }

    archives = _archives_dir(root)
    archives.mkdir(parents=True, exist_ok=True)

    iso_week = (week_start - timedelta(days=7)).strftime("%Y-W%V")
    archive_name = f"weekly-{iso_week}.zip"
    archive_path = archives / archive_name

    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(candidates):
                zf.write(f, f.name)
        for f in candidates:
            f.unlink()
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "archive_name": None,
            "files_archived": 0,
            "skipped_reason": None,
            "error": str(exc),
        }

    return {
        "ok": True,
        "archive_name": archive_name,
        "files_archived": len(candidates),
        "skipped_reason": None,
        "error": None,
    }


def consolidate_year(
    year: int | None = None,
    root: Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Bundle prior-year weekly archives into a single yearly zip.

    Returns a dict with keys:
        ok                    bool — True on success or nothing-to-do
        archive_name          str  — name of the zip created (or None)
        archives_consolidated int  — number of weekly zips bundled
        skipped_reason        str  — human-readable reason when skipped (or None)
        error                 str  — error message on failure (or None)
    """
    if root is None:
        root = get_spool_root()
    if today is None:
        today = date.today()
    if year is None:
        year = today.year - 1

    archives = _archives_dir(root)
    if not archives.exists():
        return {
            "ok": True,
            "archive_name": None,
            "archives_consolidated": 0,
            "skipped_reason": "archives/ directory does not exist",
            "error": None,
        }

    prefix = f"weekly-{year}-"
    weeklies = sorted(archives.glob(f"{prefix}*.zip"))

    if not weeklies:
        return {
            "ok": True,
            "archive_name": None,
            "archives_consolidated": 0,
            "skipped_reason": f"no weekly archives found for {year}",
            "error": None,
        }

    yearly_name = f"yearly-{year}.zip"
    yearly_path = archives / yearly_name

    try:
        with zipfile.ZipFile(yearly_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for w in weeklies:
                zf.write(w, w.name)
        for w in weeklies:
            w.unlink()
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "archive_name": None,
            "archives_consolidated": 0,
            "skipped_reason": None,
            "error": str(exc),
        }

    return {
        "ok": True,
        "archive_name": yearly_name,
        "archives_consolidated": len(weeklies),
        "skipped_reason": None,
        "error": None,
    }
