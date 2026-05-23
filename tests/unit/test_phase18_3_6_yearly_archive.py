"""Phase 18.3.6 — spool.lifecycle.consolidate_year: happy path and idempotency."""

from __future__ import annotations

import datetime
import json
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from spool.lifecycle import consolidate_year
from spool.states import SpoolState, ensure_dirs, state_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 1, 2)  # January 2 — day after consolidation trigger


def _make_weekly_archive(arch_dir: Path, date_str: str, n_events: int = 2) -> Path:
    """Create a valid weekly archive in the archives directory."""
    path = arch_dir / f"spool-processed-{date_str}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _ in range(n_events):
            eid = str(uuid.uuid4())
            zf.writestr(f"{eid}.json", json.dumps({"event_id": eid}))
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_yearly_archive_happy_path(spool_root):
    """Prior-year weekly archives → yearly archive created → weeklies deleted."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    w1 = _make_weekly_archive(arch_dir, "2025-01-06")
    w2 = _make_weekly_archive(arch_dir, "2025-06-02")
    w3 = _make_weekly_archive(arch_dir, "2025-12-29")

    result = consolidate_year(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["archives_consolidated"] == 3
    assert result["archive_name"] == "spool-processed-2025.zip"
    assert result["error"] is None
    assert result["skipped_reason"] is None

    # Yearly archive exists and is valid
    year_path = arch_dir / "spool-processed-2025.zip"
    assert year_path.exists()
    with zipfile.ZipFile(year_path, "r") as zf:
        members = {m for m in zf.namelist()}
    assert w1.name in members
    assert w2.name in members
    assert w3.name in members

    # Weekly archives removed
    assert not w1.exists()
    assert not w2.exists()
    assert not w3.exists()


def test_yearly_archive_explicit_year(spool_root):
    """year= parameter targets a specific year regardless of today."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    w = _make_weekly_archive(arch_dir, "2024-03-11")

    result = consolidate_year(year=2024, root=spool_root)

    assert result["ok"] is True
    assert result["archives_consolidated"] == 1
    assert result["archive_name"] == "spool-processed-2024.zip"
    assert not w.exists()


def test_yearly_archive_no_weeklies(spool_root):
    """No weekly archives for prior year → ok=True, skipped, no archive written."""
    ensure_dirs(spool_root)
    result = consolidate_year(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["archives_consolidated"] == 0
    assert result["skipped_reason"] == "no_weekly_archives_found"

    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    zips = list(arch_dir.glob("spool-processed-2025.zip")) if arch_dir.exists() else []
    assert len(zips) == 0


def test_yearly_archive_ignores_current_year_weeklies(spool_root):
    """Weeklies from the current year are untouched."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    _make_weekly_archive(arch_dir, "2025-12-29")       # prior year → consolidated
    current = _make_weekly_archive(arch_dir, "2026-01-06")  # current year → untouched

    result = consolidate_year(root=spool_root, today=_TODAY)

    assert result["archives_consolidated"] == 1
    assert current.exists()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_yearly_archive_idempotent_already_exists(spool_root):
    """If yearly archive already exists, return immediately without touching weeklies."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    w = _make_weekly_archive(arch_dir, "2025-09-01")

    # Pre-create the yearly archive
    year_path = arch_dir / "spool-processed-2025.zip"
    with zipfile.ZipFile(year_path, "w") as zf:
        zf.writestr("placeholder.txt", "already done")

    result = consolidate_year(root=spool_root, today=_TODAY)

    assert result["ok"] is True
    assert result["skipped_reason"] == "already_exists"
    assert result["archives_consolidated"] == 0
    # Weekly NOT deleted — idempotency does not clean up originals in this mode
    assert w.exists()


def test_yearly_archive_no_duplicate_zip(spool_root):
    """Running consolidate_year twice creates exactly one yearly zip."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    _make_weekly_archive(arch_dir, "2025-07-07")

    r1 = consolidate_year(root=spool_root, today=_TODAY)
    assert r1["archives_consolidated"] == 1

    r2 = consolidate_year(root=spool_root, today=_TODAY)
    assert r2["skipped_reason"] == "already_exists"

    yearly_zips = list(arch_dir.glob("spool-processed-2025.zip"))
    assert len(yearly_zips) == 1


def test_yearly_archive_second_run_no_weeklies(spool_root):
    """After weeklies are deleted by first run, second run finds nothing and is safe."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    _make_weekly_archive(arch_dir, "2025-04-07")

    r1 = consolidate_year(root=spool_root, today=_TODAY)
    assert r1["archives_consolidated"] == 1

    # Delete the yearly archive to simulate a fresh run scenario
    (arch_dir / "spool-processed-2025.zip").unlink()

    # Now no weeklies exist either
    r2 = consolidate_year(root=spool_root, today=_TODAY)
    assert r2["archives_consolidated"] == 0
    assert r2["skipped_reason"] == "no_weekly_archives_found"


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_yearly_archive_verify_fail_preserves_weeklies(spool_root):
    """If zip verification fails, weekly archives are preserved and ok=False returned."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    w = _make_weekly_archive(arch_dir, "2025-05-19")

    with patch("spool.lifecycle._verify_zip", return_value=False):
        result = consolidate_year(root=spool_root, today=_TODAY)

    assert result["ok"] is False
    assert "verification failed" in result["error"]
    assert result["archives_consolidated"] == 0

    # Weekly archive must still exist
    assert w.exists()

    # No corrupt yearly archive left
    bad = arch_dir / "spool-processed-2025.zip"
    assert not bad.exists()


def test_yearly_archive_zip_creation_failure_preserves_weeklies(spool_root):
    """If zip writing raises, weekly archives are preserved."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)

    w = _make_weekly_archive(arch_dir, "2025-02-17")

    with patch("zipfile.ZipFile.__init__", side_effect=OSError("disk full")):
        result = consolidate_year(root=spool_root, today=_TODAY)

    assert result["ok"] is False
    assert w.exists()
