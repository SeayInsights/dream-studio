"""Phase 18.3.6 — spool_restore.py: disaster recovery round-trip tests."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import the restore script as a module
# ---------------------------------------------------------------------------

_RESTORE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "spool_restore.py"


def _load_restore():
    spec = importlib.util.spec_from_file_location("spool_restore", _RESTORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules so unittest.mock.patch can find it by name
    sys.modules["spool_restore"] = mod
    spec.loader.exec_module(mod)
    return mod


restore = _load_restore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event_json() -> tuple[str, str]:
    """Return (filename, json_content) for a minimal valid event."""
    eid = str(uuid.uuid4())
    content = json.dumps(
        {
            "event_id": eid,
            "event_type": "test.restore_event",
            "timestamp": "2026-05-22T12:00:00+00:00",
            "schema_version": 1,
            "payload": {},
        }
    )
    return f"{eid}.json", content


def _make_weekly_archive(arch_dir: Path, date_str: str, n: int = 3) -> Path:
    """Create a weekly archive with n event JSON files."""
    path = arch_dir / f"spool-processed-{date_str}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _ in range(n):
            fname, content = _make_event_json()
            zf.writestr(fname, content)
    return path


def _make_yearly_archive(arch_dir: Path, year: int, weekly_count: int = 2) -> Path:
    """Create a yearly archive containing weekly_count embedded weekly zips."""
    path = arch_dir / f"spool-processed-{year}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        for i in range(weekly_count):
            # Build a weekly zip in memory
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as inner:
                fname, content = _make_event_json()
                inner.writestr(fname, content)
            outer.writestr(f"spool-processed-{year}-01-{13 + i * 7:02d}.zip", buf.getvalue())
    return path


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------


def test_classify_weekly():
    assert restore._classify("spool-processed-2026-05-11.zip") == "weekly"


def test_classify_yearly():
    assert restore._classify("spool-processed-2025.zip") == "yearly"


def test_classify_invalid():
    with pytest.raises(ValueError, match="does not match"):
        restore._classify("unknown-archive.zip")


# ---------------------------------------------------------------------------
# _json_members
# ---------------------------------------------------------------------------


def test_json_members_filters_non_json(tmp_path):
    zp = tmp_path / "test.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("a.json", '{}')
        zf.writestr("b.txt", "text")
        zf.writestr("c.json", '{}')
    with zipfile.ZipFile(zp, "r") as zf:
        members = restore._json_members(zf)
    names = [m.filename for m in members]
    assert "a.json" in names
    assert "c.json" in names
    assert "b.txt" not in names


# ---------------------------------------------------------------------------
# restore_weekly — dry run
# ---------------------------------------------------------------------------


def test_restore_weekly_dry_run_prints_summary(spool_root, capsys):
    """Dry run prints archive info without writing anything."""
    from spool.states import SpoolState, ensure_dirs, state_dir

    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    archive_path = _make_weekly_archive(arch_dir, "2026-05-11", n=4)
    inbox = state_dir(SpoolState.SPOOL, spool_root)

    restore.restore_weekly(
        archive_path,
        inbox,
        dry_run=True,
        db_path=None,
        root=spool_root,
    )

    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "4 events" in out
    assert "No changes made" in out

    # No files extracted
    assert list(inbox.glob("*.json")) == []


# ---------------------------------------------------------------------------
# restore_weekly — actual replay (mocked ingestor)
# ---------------------------------------------------------------------------


def test_restore_weekly_extracts_files_to_inbox(spool_root):
    """restore_weekly copies event files into the spool inbox."""
    from spool.states import SpoolState, ensure_dirs, state_dir

    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    archive_path = _make_weekly_archive(arch_dir, "2026-05-11", n=2)
    inbox = state_dir(SpoolState.SPOOL, spool_root)

    fake_result = MagicMock()
    fake_result.processed = 2
    fake_result.failed = 0
    fake_result.skipped = 0

    with patch("spool_restore.ingest_pending", return_value=fake_result) as mock_ingest:
        restore.restore_weekly(
            archive_path,
            inbox,
            dry_run=False,
            db_path=None,
            root=spool_root,
        )

    # All event files were extracted to inbox before ingest was called
    extracted = list(inbox.glob("*.json"))
    assert len(extracted) == 2

    # ingest_pending was called with the correct root
    mock_ingest.assert_called_once_with(root=spool_root, db_path=None)


def test_restore_weekly_skip_already_present(spool_root):
    """Files already in the inbox are skipped (idempotency)."""
    from spool.states import SpoolState, ensure_dirs, state_dir

    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    inbox = state_dir(SpoolState.SPOOL, spool_root)

    # Create archive
    archive_path = arch_dir / "spool-processed-2026-05-11.zip"
    fname, content = _make_event_json()
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr(fname, content)

    # Pre-populate inbox with the same file
    (inbox / fname).write_text(content, encoding="utf-8")

    fake_result = MagicMock(processed=0, failed=0, skipped=1)
    with patch("spool_restore.ingest_pending", return_value=fake_result):
        restore.restore_weekly(archive_path, inbox, dry_run=False, db_path=None, root=spool_root)

    # Still one file (not duplicated)
    assert len(list(inbox.glob("*.json"))) == 1


# ---------------------------------------------------------------------------
# restore_yearly — dry run
# ---------------------------------------------------------------------------


def test_restore_yearly_dry_run_prints_summary(spool_root, capsys):
    """Yearly dry run reports event count without writes."""
    from spool.states import SpoolState, ensure_dirs, state_dir

    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    archive_path = _make_yearly_archive(arch_dir, 2025, weekly_count=2)
    inbox = state_dir(SpoolState.SPOOL, spool_root)

    restore.restore_yearly(
        archive_path,
        inbox,
        dry_run=True,
        db_path=None,
        root=spool_root,
    )

    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "2 events" in out
    assert "No changes made" in out


# ---------------------------------------------------------------------------
# Full round-trip: archive_week → restore (mocked ingestor)
# ---------------------------------------------------------------------------


def test_round_trip_weekly_archive_then_restore(spool_root, tmp_path):
    """Full round-trip: lifecycle creates archive → restore replays into fresh root."""
    import datetime
    import os

    from spool.lifecycle import archive_week
    from spool.states import SpoolState, ensure_dirs, state_dir

    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)

    # Write event files and backdate to prior week
    event_ids = []
    today = datetime.date.today()
    from spool.lifecycle import _prior_week_monday, _week_timestamps

    pm = _prior_week_monday(today)
    start_ts, _ = _week_timestamps(pm)
    mid_ts = start_ts + 3600  # 1 hour into the prior week

    for _ in range(3):
        eid = str(uuid.uuid4())
        f = processed_dir / f"{eid}.json"
        f.write_text(json.dumps({"event_id": eid, "event_type": "test.event", "schema_version": 1}))
        os.utime(f, (mid_ts, mid_ts))
        event_ids.append(eid)

    # Step 1: archive
    result = archive_week(root=spool_root, today=today)
    assert result["ok"] is True
    assert result["files_archived"] == 3

    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    archive_path = arch_dir / result["archive_name"]
    assert archive_path.exists()

    # Verify the archive contains all three events
    with zipfile.ZipFile(archive_path, "r") as zf:
        archived_names = {Path(n).stem for n in zf.namelist()}
    assert set(event_ids) == archived_names

    # Step 2: restore into a fresh spool root
    restore_root = tmp_path / "restore_root"
    restore_root.mkdir()
    from spool.states import ensure_dirs as ed
    ed(restore_root)

    restore_inbox = state_dir(SpoolState.SPOOL, restore_root)

    fake_result = MagicMock(processed=3, failed=0, skipped=0)
    with patch("spool_restore.ingest_pending", return_value=fake_result) as mock_ingest:
        restore.restore_weekly(
            archive_path,
            restore_inbox,
            dry_run=False,
            db_path=None,
            root=restore_root,
        )

    # All event files were placed into the restore inbox
    restored_ids = {f.stem for f in restore_inbox.glob("*.json")}
    assert set(event_ids) == restored_ids

    # ingest_pending was called
    mock_ingest.assert_called_once()
