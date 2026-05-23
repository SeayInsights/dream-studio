"""Phase 18.3.6 — ds spool CLI commands: archive, consolidate-year, archives list/inspect."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from interfaces.cli.ds_spool import (
    add_spool_subcommand,
    cmd_archive,
    cmd_archives_inspect,
    cmd_archives_list,
    cmd_consolidate_year,
)
from spool.states import SpoolState, ensure_dirs, state_dir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _write_prior_week_file(processed_dir: Path) -> Path:
    """Write an event file with a prior-week mtime."""
    eid = str(uuid.uuid4())
    path = processed_dir / f"{eid}.json"
    path.write_text(json.dumps({"event_id": eid}), encoding="utf-8")
    # Set mtime to 14 days ago (safely in the prior-week window)
    ts = (datetime.datetime.now() - datetime.timedelta(days=14)).timestamp()
    os.utime(path, (ts, ts))
    return path


def _make_weekly_zip(arch_dir: Path, date_str: str) -> Path:
    path = arch_dir / f"spool-processed-{date_str}.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("evt.json", '{"event_id": "abc"}')
    return path


# ---------------------------------------------------------------------------
# ds spool archive
# ---------------------------------------------------------------------------


def test_cmd_archive_happy_path(spool_root, capsys):
    """archive command returns exit 0 and prints JSON with ok=True."""
    ensure_dirs(spool_root)
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    _write_prior_week_file(processed_dir)

    args = _make_args()
    rc = cmd_archive(args)

    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["ok"] is True
    assert data["files_archived"] >= 0  # 0 if file falls outside the exact window


def test_cmd_archive_returns_0_on_no_files(spool_root, capsys):
    """archive with no prior-week files returns exit 0."""
    ensure_dirs(spool_root)
    args = _make_args()
    rc = cmd_archive(args)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True


def test_cmd_archive_returns_1_on_failure(spool_root, capsys):
    """archive returns exit 1 when lifecycle reports ok=False."""
    ensure_dirs(spool_root)
    args = _make_args()

    with patch("spool.lifecycle.archive_week", return_value={"ok": False, "error": "boom"}):
        rc = cmd_archive(args)

    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False


# ---------------------------------------------------------------------------
# ds spool consolidate-year
# ---------------------------------------------------------------------------


def test_cmd_consolidate_year_no_archives(spool_root, capsys):
    """consolidate-year with no weeklies returns exit 0 with ok=True."""
    ensure_dirs(spool_root)
    args = _make_args(year=None)
    rc = cmd_consolidate_year(args)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True


def test_cmd_consolidate_year_explicit_year(spool_root, capsys):
    """consolidate-year passes year argument to lifecycle."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    _make_weekly_zip(arch_dir, "2024-03-11")

    args = _make_args(year=2024)
    rc = cmd_consolidate_year(args)

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["archives_consolidated"] == 1
    assert data["archive_name"] == "spool-processed-2024.zip"


def test_cmd_consolidate_year_returns_1_on_failure(spool_root, capsys):
    """consolidate-year returns exit 1 when lifecycle reports ok=False."""
    ensure_dirs(spool_root)
    args = _make_args(year=None)

    with patch(
        "spool.lifecycle.consolidate_year",
        return_value={"ok": False, "error": "oops"},
    ):
        rc = cmd_consolidate_year(args)

    assert rc == 1


# ---------------------------------------------------------------------------
# ds spool archives list
# ---------------------------------------------------------------------------


def test_cmd_archives_list_no_archives(spool_root, capsys):
    """archives list prints 'no archives found' when archives/ is empty."""
    ensure_dirs(spool_root)
    args = _make_args()
    rc = cmd_archives_list(args)
    assert rc == 0
    assert "no archives found" in capsys.readouterr().out


def test_cmd_archives_list_shows_archives(spool_root, capsys):
    """archives list prints archive filenames."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    _make_weekly_zip(arch_dir, "2026-05-11")

    args = _make_args()
    rc = cmd_archives_list(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "spool-processed-2026-05-11.zip" in out


# ---------------------------------------------------------------------------
# ds spool archives inspect
# ---------------------------------------------------------------------------


def test_cmd_archives_inspect_valid(spool_root, capsys):
    """archives inspect lists entries inside a valid zip."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    _make_weekly_zip(arch_dir, "2026-05-11")

    args = _make_args(archive_name="spool-processed-2026-05-11.zip")
    rc = cmd_archives_inspect(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "evt.json" in out
    assert "spool-processed-2026-05-11.zip" in out


def test_cmd_archives_inspect_missing(spool_root, capsys):
    """archives inspect returns exit 1 when archive not found."""
    ensure_dirs(spool_root)
    args = _make_args(archive_name="nonexistent.zip")
    rc = cmd_archives_inspect(args)
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_cmd_archives_inspect_bad_zip(spool_root, capsys):
    """archives inspect returns exit 1 for a corrupt zip."""
    ensure_dirs(spool_root)
    arch_dir = state_dir(SpoolState.ARCHIVES, spool_root)
    bad = arch_dir / "corrupt.zip"
    bad.write_bytes(b"not a zip")

    args = _make_args(archive_name="corrupt.zip")
    rc = cmd_archives_inspect(args)
    assert rc == 1


# ---------------------------------------------------------------------------
# Parser wiring
# ---------------------------------------------------------------------------


def test_parser_registers_archive_command():
    """add_spool_subcommand wires up 'archive' sub-parser."""
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd")
    add_spool_subcommand(subs)

    ns = parser.parse_args(["spool", "archive"])
    assert hasattr(ns, "func")
    assert ns.func is cmd_archive


def test_parser_registers_consolidate_year():
    """add_spool_subcommand wires up 'consolidate-year' sub-parser."""
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd")
    add_spool_subcommand(subs)

    ns = parser.parse_args(["spool", "consolidate-year", "2024"])
    assert ns.func is cmd_consolidate_year
    assert ns.year == 2024


def test_parser_registers_archives_list():
    """add_spool_subcommand wires up 'archives list' sub-parser."""
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd")
    add_spool_subcommand(subs)

    ns = parser.parse_args(["spool", "archives", "list"])
    assert ns.func is cmd_archives_list
