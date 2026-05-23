"""Spool processed-file lifecycle: weekly and yearly archiving (OD8).

Directory layout under the spool root (~/.dream-studio/events/ by default):
  processed/   — JSON files successfully ingested; managed here
  archives/    — weekly zips + yearly zip-of-zips

Weekly archive (Monday-anchored):
  Run on each Monday; bundles the Monday-Sunday week that just ended into
  spool-processed-YYYY-MM-DD.zip (date = the prior Monday).

Yearly consolidation (January 1):
  Run on 1 Jan; bundles all prior-year weekly archives into
  spool-processed-YYYY.zip, then removes the weekly archives.

Both operations are idempotent: if the target archive already exists the
function returns immediately without touching existing files.
"""

from __future__ import annotations

import datetime
import logging
import zipfile
from pathlib import Path
from typing import Optional

from spool.config import get_spool_root
from spool.states import SpoolState, ensure_dirs, state_dir

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _archives_dir(root: Path) -> Path:
    d = root / SpoolState.ARCHIVES.value
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prior_week_monday(today: datetime.date) -> datetime.date:
    """Monday of the week that ended before today's Monday."""
    days_since_monday = today.weekday()  # Monday=0, Sunday=6
    this_monday = today - datetime.timedelta(days=days_since_monday)
    return this_monday - datetime.timedelta(weeks=1)


def _week_timestamps(monday: datetime.date) -> tuple[float, float]:
    """Return (start_ts, exclusive_end_ts) spanning Mon 00:00 through Sun 23:59:59."""
    start = datetime.datetime(monday.year, monday.month, monday.day)
    end = start + datetime.timedelta(weeks=1)
    return start.timestamp(), end.timestamp()


def _verify_zip(path: Path, expected_count: int) -> bool:
    """Return True if the zip is intact and contains exactly expected_count entries."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                logger.error("Zip integrity failure in %s: first bad file = %s", path.name, bad)
                return False
            actual = len(zf.namelist())
            if actual != expected_count:
                logger.error(
                    "Zip entry count mismatch for %s: expected %d, got %d",
                    path.name,
                    expected_count,
                    actual,
                )
                return False
    except (zipfile.BadZipFile, OSError) as exc:
        logger.error("Could not open zip %s: %s", path.name, exc)
        return False
    return True


# ── Public API ────────────────────────────────────────────────────────────────


def archive_week(
    root: Optional[Path] = None,
    today: Optional[datetime.date] = None,
) -> dict:
    """Bundle prior-week processed files into a dated zip.

    Returns a result dict:
      ok              bool
      archive_name    str  — filename (not full path)
      files_archived  int
      skipped_reason  str | None  — set when ok=True but nothing was done
      error           str | None  — set when ok=False
    """
    r = root if root is not None else get_spool_root()
    ensure_dirs(r)
    processed_dir = state_dir(SpoolState.PROCESSED, r)
    archives = _archives_dir(r)

    today = today or datetime.date.today()
    prior_monday = _prior_week_monday(today)
    archive_name = f"spool-processed-{prior_monday.isoformat()}.zip"
    archive_path = archives / archive_name

    if archive_path.exists():
        return {
            "ok": True,
            "archive_name": archive_name,
            "files_archived": 0,
            "skipped_reason": "already_exists",
            "error": None,
        }

    start_ts, end_ts = _week_timestamps(prior_monday)
    candidates: list[Path] = []
    try:
        for f in processed_dir.glob("*.json"):
            mtime = f.stat().st_mtime
            if start_ts <= mtime < end_ts:
                candidates.append(f)
    except OSError as exc:
        return {
            "ok": False,
            "archive_name": archive_name,
            "files_archived": 0,
            "skipped_reason": None,
            "error": f"listing processed/ failed: {exc}",
        }

    if not candidates:
        return {
            "ok": True,
            "archive_name": archive_name,
            "files_archived": 0,
            "skipped_reason": "no_files_in_window",
            "error": None,
        }

    tmp_path = archive_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in candidates:
                zf.write(f, arcname=f.name)
        tmp_path.replace(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "ok": False,
            "archive_name": archive_name,
            "files_archived": 0,
            "skipped_reason": None,
            "error": f"zip creation failed: {exc}",
        }

    if not _verify_zip(archive_path, len(candidates)):
        logger.error(
            "Weekly archive %s failed verification; originals preserved.", archive_name
        )
        try:
            archive_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "ok": False,
            "archive_name": archive_name,
            "files_archived": 0,
            "skipped_reason": None,
            "error": "zip verification failed; originals preserved",
        }

    deleted = 0
    for f in candidates:
        try:
            f.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Could not delete archived file %s: %s", f.name, exc)

    logger.info(
        "Weekly archive created: %s (%d files, %d deleted)",
        archive_name,
        len(candidates),
        deleted,
    )
    return {
        "ok": True,
        "archive_name": archive_name,
        "files_archived": len(candidates),
        "skipped_reason": None,
        "error": None,
    }


def consolidate_year(
    year: Optional[int] = None,
    root: Optional[Path] = None,
    today: Optional[datetime.date] = None,
) -> dict:
    """Bundle prior-year weekly archives into a single yearly zip.

    If *year* is not supplied, consolidates the prior calendar year.

    Returns a result dict:
      ok                    bool
      archive_name          str
      archives_consolidated int
      skipped_reason        str | None
      error                 str | None
    """
    r = root if root is not None else get_spool_root()
    ensure_dirs(r)
    archives = _archives_dir(r)

    today = today or datetime.date.today()
    target_year = year if year is not None else today.year - 1
    year_archive_name = f"spool-processed-{target_year}.zip"
    year_archive_path = archives / year_archive_name

    if year_archive_path.exists():
        return {
            "ok": True,
            "archive_name": year_archive_name,
            "archives_consolidated": 0,
            "skipped_reason": "already_exists",
            "error": None,
        }

    prefix = f"spool-processed-{target_year}-"
    weekly: list[Path] = []
    try:
        for f in archives.glob(f"spool-processed-{target_year}-*.zip"):
            if f.name.startswith(prefix) and f.suffix == ".zip":
                weekly.append(f)
    except OSError as exc:
        return {
            "ok": False,
            "archive_name": year_archive_name,
            "archives_consolidated": 0,
            "skipped_reason": None,
            "error": f"listing archives/ failed: {exc}",
        }

    if not weekly:
        return {
            "ok": True,
            "archive_name": year_archive_name,
            "archives_consolidated": 0,
            "skipped_reason": "no_weekly_archives_found",
            "error": None,
        }

    tmp_path = year_archive_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for wf in weekly:
                zf.write(wf, arcname=wf.name)
        tmp_path.replace(year_archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "ok": False,
            "archive_name": year_archive_name,
            "archives_consolidated": 0,
            "skipped_reason": None,
            "error": f"zip creation failed: {exc}",
        }

    if not _verify_zip(year_archive_path, len(weekly)):
        logger.error(
            "Yearly archive %s failed verification; weekly archives preserved.",
            year_archive_name,
        )
        try:
            year_archive_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "ok": False,
            "archive_name": year_archive_name,
            "archives_consolidated": 0,
            "skipped_reason": None,
            "error": "zip verification failed; weekly archives preserved",
        }

    deleted = 0
    for wf in weekly:
        try:
            wf.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Could not delete weekly archive %s: %s", wf.name, exc)

    logger.info(
        "Yearly archive created: %s (%d weekly archives, %d deleted)",
        year_archive_name,
        len(weekly),
        deleted,
    )
    return {
        "ok": True,
        "archive_name": year_archive_name,
        "archives_consolidated": len(weekly),
        "skipped_reason": None,
        "error": None,
    }


def check_and_archive(root: Optional[Path] = None) -> None:
    """Run lifecycle operations if scheduled conditions are met.

    Called by the projection runner daemon at startup and every 24 hours.
    Safe to call at any time — all operations are idempotent.

    - Mondays: run weekly archive
    - January 1: run yearly consolidation (after the weekly archive)
    """
    today = datetime.date.today()

    if today.weekday() == 0:  # Monday
        try:
            result = archive_week(root=root, today=today)
            if result["ok"] and result["files_archived"] > 0:
                logger.info(
                    "[lifecycle] Weekly archive: %s (%d files)",
                    result["archive_name"],
                    result["files_archived"],
                )
            elif not result["ok"]:
                logger.warning("[lifecycle] Weekly archive failed: %s", result.get("error"))
        except Exception:
            logger.exception("[lifecycle] Weekly archive raised unexpectedly")

    if today.month == 1 and today.day == 1:
        try:
            result = consolidate_year(root=root, today=today)
            if result["ok"] and result["archives_consolidated"] > 0:
                logger.info(
                    "[lifecycle] Yearly consolidation: %s (%d archives)",
                    result["archive_name"],
                    result["archives_consolidated"],
                )
            elif not result["ok"]:
                logger.warning(
                    "[lifecycle] Yearly consolidation failed: %s", result.get("error")
                )
        except Exception:
            logger.exception("[lifecycle] Yearly consolidation raised unexpectedly")
