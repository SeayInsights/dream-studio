"""`ds doctor` is read-only, and it says how much business data the authority holds.

It reported `doctor_runs_read_only: True` while writing: it refreshed the platform
profile, opened the authority through the migrating connection (applying migrations,
switching journal mode), and wrote the main-CI status cache into the authority.
And it never looked at whether the authority still HELD anything: the empty
replacement of 2026-09-23 passed every doctor check, because a schema-complete
database with zero projects is perfectly healthy by every measure doctor took.

These run the real CLI in a subprocess against a temporary home holding one
project, snapshot every file under that home (and the Claude config root it reads)
before and after, and require them byte-identical. They also check the row counts
and the drop warning.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _env(tmp: Path) -> dict[str, str]:
    # Nothing inherited: DS_PLATFORM_PROFILE_PATH, DS_SPOOL_ROOT and friends redirect
    # writes out of the home this test snapshots, and DREAM_STUDIO_APPLY_UNRELEASED hides
    # the schema an operator's authority actually has (the shipped released version).
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DREAM_STUDIO_DB_PATH"] = str(tmp / "home" / "state" / "studio.db")
    env["CLAUDE_CONFIG_DIR"] = str(tmp / "claude")
    env["HOME"] = str(tmp / "userhome")
    env["USERPROFILE"] = str(tmp / "userhome")
    return env


def _ds(tmp: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(tmp / "home"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp / "work",
        env=_env(tmp),
        timeout=900,
    )


def _snapshot(*roots: Path) -> dict[str, str]:
    snap: dict[str, str] = {}
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                path = Path(dirpath) / name
                snap[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


@pytest.fixture(scope="module")
def populated(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("doctor")
    for sub in ("home", "claude", "userhome", "work", "project"):
        (tmp / sub).mkdir()
    from core.config.sqlite_bootstrap import bootstrap_database, shipped_released_version

    # The schema a live authority has: up to the SHIPPED released version, not past it.
    bootstrap_database(
        tmp / "home" / "state" / "studio.db", target_version=shipped_released_version()
    )
    proc = _ds(tmp, "project", "register", "--name", "Doctor Demo", "--path", str(tmp / "project"))
    assert proc.returncode == 0, proc.stderr[-2000:]
    return tmp


def _doctor(tmp: Path, *extra: str) -> dict:
    proc = _ds(tmp, "doctor", *extra)
    assert proc.returncode in (0, 1), proc.stderr[-2000:]
    start = proc.stdout.index("{")
    return json.loads(proc.stdout[start:])


def test_doctor_writes_nothing(populated):
    roots = (populated / "home", populated / "claude", populated / "userhome")
    before = _snapshot(*roots)
    report = _doctor(populated)
    after = _snapshot(*roots)

    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not changed, f"ds doctor wrote: {changed}"
    assert report["checks"]["doctor_runs_read_only"] is True


def test_doctor_reports_business_row_counts(populated):
    report = _doctor(populated)
    authority = report["checks"]["authority_data"]
    assert authority["counts"]["projects"] >= 1
    assert set(authority["counts"]) == {"projects", "work_orders", "tasks", "events"}
    assert authority["readable"] is True


def test_doctor_warns_on_zero_and_on_a_drop_against_recorded_counts(populated):
    # Record a baseline explicitly (the one write, opt-in), then lose the project.
    proc = _ds(populated, "doctor", "--record-counts")
    assert proc.returncode in (0, 1), proc.stderr[-2000:]
    db = populated / "home" / "state" / "studio.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM business_projects")
        conn.commit()
    finally:
        conn.close()

    authority = _doctor(populated)["checks"]["authority_data"]
    warnings = " ".join(authority["warnings"])
    assert authority["counts"]["projects"] == 0
    assert "projects" in warnings and "dropped" in warnings
    assert "zero" in warnings or "empty" in warnings
    assert authority["last_recorded"]["counts"]["projects"] >= 1


def test_doctor_names_the_code_root_it_runs_from(populated):
    report = _doctor(populated)
    app = report["checks"]["installed_app"]
    assert Path(app["code_root"]).resolve() == REPO
    assert app["running_from_checkout"] is True


@pytest.mark.parametrize("marked", [False, True], ids=["fresh-home", "installed-home"])
def test_doctor_writes_nothing_when_there_is_no_authority(tmp_path, marked):
    for sub in ("home", "claude", "userhome", "work"):
        (tmp_path / sub).mkdir()
    if marked:
        (tmp_path / "home" / "state").mkdir()
        (tmp_path / "home" / "state" / "installed-version").write_text("0.1.0 abc\n")
    roots = (tmp_path / "home", tmp_path / "claude", tmp_path / "userhome")
    before = _snapshot(*roots)
    _doctor(tmp_path)
    after = _snapshot(*roots)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not changed, f"ds doctor wrote: {changed}"
