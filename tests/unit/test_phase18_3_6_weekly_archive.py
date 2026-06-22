"""Phase 18.3.6 — spool.lifecycle.archive_week: happy path, idempotency, failure handling."""

from __future__ import annotations

import datetime
import json
import os
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from spool.lifecycle import _prior_week_monday, _week_timestamps, archive_week
from spool.states import SpoolState, ensure_dirs, state_dir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 5, 20)  # Wednesday — stable anchor for all tests


def _prior_monday() -> datetime.date:
    return _prior_week_monday(_TODAY)


def _write_event(processed_dir: Path, event_type: str = "test.event") -> Path:
    """Write a minimal valid event JSON and return its path."""
    event_id = str(uuid.uuid4())
    path = processed_dir / f"{event_id}.json"
    path.write_text(
        json.dumps({"event_id": event_id, "event_type": event_type, "schema_version": 1}),
        encoding="utf-8",
    )
    return path


def _set_mtime_in_prior_week(path: Path) -> None:
    """Set file mtime to Monday 06:00 of the prior week (within the archive window)."""
    monday = _prior_monday()
    ts = datetime.datetime(monday.year, monday.month, monday.day, 6, 0, 0).timestamp()
    os.utime(path, (ts, ts))


def _set_mtime_in_current_week(path: Path) -> None:
    """Set file mtime to today (outside the prior-week archive window)."""
    # File already has current mtime from write; this is a no-op but makes intent clear.


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_weekly_archive_happy_path(spool_root):
    """Prior-week files → archive created → originals deleted."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)

    f1 = _write_event(processed_dir)
    f2 = _write_event(processed_dir)
    _set_mtime_in_prior_week(f1)
    _set_mtime_in_prior_week(f2)

    result = archive_week(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["files_archived"] == 2
    assert result["error"] is None
    assert result["skipped_reason"] is None

    expected_name = f"spool-processed-{_prior_monday().isoformat()}.zip"
    assert result["archive_name"] == expected_name

    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    archive_path = arch_dir / expected_name
    assert archive_path.exists()

    # Originals deleted
    assert not f1.exists()
    assert not f2.exists()

    # Both files are in the archive
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()
    assert f1.name in names
    assert f2.name in names


def test_weekly_archive_current_week_files_stay_loose(spool_root):
    """Files written this week are not included in the prior-week archive."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)

    old_file = _write_event(processed_dir)
    _set_mtime_in_prior_week(old_file)

    new_file = _write_event(processed_dir)
    # new_file mtime is now (current week) — must not be archived

    result = archive_week(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["files_archived"] == 1
    assert not old_file.exists()
    assert new_file.exists()  # untouched

    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    archive_name = result["archive_name"]
    with zipfile.ZipFile(arch_dir / archive_name, "r") as zf:
        names = zf.namelist()
    assert old_file.name in names
    assert new_file.name not in names


def test_weekly_archive_no_prior_week_files(spool_root):
    """No files in the prior-week window → ok=True, skipped_reason set, no archive written."""
    ensure_dirs(spool_root)
    # Write a current-week file only — not in window
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    _write_event(processed_dir)

    result = archive_week(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["files_archived"] == 0
    assert result["skipped_reason"] == "no_files_in_window"
    assert result["error"] is None

    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    zips = list(arch_dir.glob("*.zip")) if arch_dir.exists() else []
    assert len(zips) == 0


def test_weekly_archive_empty_processed_dir(spool_root):
    """Empty processed/ → ok=True, nothing written."""
    ensure_dirs(spool_root)
    result = archive_week(root=spool_root, today=_TODAY)
    assert result["ok"] is True
    assert result["files_archived"] == 0


def test_weekly_archive_archive_name_matches_prior_monday(spool_root):
    """Archive filename encodes the prior Monday's ISO date."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    f = _write_event(processed_dir)
    _set_mtime_in_prior_week(f)

    result = archive_week(root=spool_root, today=_TODAY)

    expected = f"spool-processed-{_prior_monday().isoformat()}.zip"
    assert result["archive_name"] == expected


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_weekly_archive_idempotent_archive_already_exists(spool_root):
    """If the target archive already exists, return immediately without touching originals."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    f = _write_event(processed_dir)
    _set_mtime_in_prior_week(f)

    # Pre-create the archive (simulates a previous run)
    archive_name = f"spool-processed-{_prior_monday().isoformat()}.zip"
    archive_path = arch_dir / archive_name
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("placeholder.txt", "already done")

    result = archive_week(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["skipped_reason"] == "already_exists"
    assert result["files_archived"] == 0
    # Original file was NOT touched
    assert f.exists()


def test_weekly_archive_idempotent_no_duplicate_zip(spool_root):
    """Running archive_week twice creates exactly one zip."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    f = _write_event(processed_dir)
    _set_mtime_in_prior_week(f)

    r1 = archive_week(root=spool_root, today=_TODAY)
    assert r1["files_archived"] == 1

    r2 = archive_week(root=spool_root, today=_TODAY)
    assert r2["skipped_reason"] == "already_exists"

    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    zips = list(arch_dir.glob("spool-processed-*.zip"))
    assert len(zips) == 1, f"Expected 1 archive, found: {[z.name for z in zips]}"


# ---------------------------------------------------------------------------
# Failure handling — corrupted / failed archive
# ---------------------------------------------------------------------------


def test_weekly_archive_verify_fail_preserves_originals(spool_root):
    """If zip verification fails, originals are preserved and ok=False returned."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    f = _write_event(processed_dir)
    _set_mtime_in_prior_week(f)

    with patch("spool.lifecycle._verify_zip", return_value=False):
        result = archive_week(root=spool_root, today=_TODAY)

    assert result["ok"] is False
    assert "verification failed" in result["error"]
    assert result["files_archived"] == 0

    # Original must still exist
    assert f.exists()

    # No corrupt archive left on disk
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    zips = list(arch_dir.glob("*.zip")) if arch_dir.exists() else []
    assert len(zips) == 0


def test_weekly_archive_zip_creation_failure_preserves_originals(spool_root):
    """If zip writing fails, originals are preserved and ok=False returned."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    f = _write_event(processed_dir)
    _set_mtime_in_prior_week(f)

    with patch("zipfile.ZipFile.__init__", side_effect=OSError("disk full")):
        result = archive_week(root=spool_root, today=_TODAY)

    assert result["ok"] is False
    assert f.exists()


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


def test_prior_week_monday_on_wednesday():
    """_prior_week_monday for a Wednesday returns the Monday two weeks ago."""
    today = datetime.date(2026, 5, 20)  # Wednesday
    assert _prior_week_monday(today) == datetime.date(2026, 5, 11)


def test_prior_week_monday_on_monday():
    """_prior_week_monday on Monday itself returns the prior Monday."""
    today = datetime.date(2026, 5, 18)  # Monday
    assert _prior_week_monday(today) == datetime.date(2026, 5, 11)


def test_week_timestamps_span_exactly_seven_days():
    monday = datetime.date(2026, 5, 11)
    start, end = _week_timestamps(monday)
    assert end - start == 7 * 86400
