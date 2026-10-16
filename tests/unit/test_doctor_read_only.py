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


def _baseline(tmp: Path) -> dict:
    return json.loads((tmp / "home" / "state" / "authority-counts.json").read_text("utf-8"))


def test_a_drop_is_attention_and_record_counts_will_not_bury_it(populated):
    """Round-table S4: a drop used to leave the doctor at status pass and exit 0, and
    `--record-counts` recorded the smaller numbers as the new normal before checking."""
    proc = _ds(populated, "doctor", "--record-counts")
    assert proc.returncode == 0, proc.stdout[-1500:]
    recorded = _baseline(populated)["counts"]["projects"]
    assert recorded >= 1
    db = populated / "home" / "state" / "studio.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM business_projects")
        conn.commit()
    finally:
        conn.close()

    proc = _ds(populated, "doctor")
    start = proc.stdout.index("{")
    report = json.loads(proc.stdout[start:])
    authority = report["checks"]["authority_data"]
    assert authority["counts"]["projects"] == 0
    assert any("projects" in w and "dropped" in w for w in authority["warnings"])
    assert report["status"] in ("attention_required", "fail")
    assert proc.returncode == 1, "a drop must not exit 0"

    proc = _ds(populated, "doctor", "--record-counts")
    assert proc.returncode == 1
    assert "--accept-drop" in proc.stdout + proc.stderr
    assert _baseline(populated)["counts"]["projects"] == recorded, "the drop was recorded"

    proc = _ds(populated, "doctor", "--record-counts", "--accept-drop")
    assert _baseline(populated)["counts"]["projects"] == 0
    report = _doctor(populated)
    assert not report["checks"]["authority_data"]["warnings"]


def test_empty_tables_without_a_baseline_are_notes_not_warnings(tmp_path):
    for sub in ("home", "claude", "userhome", "work"):
        (tmp_path / sub).mkdir()
    from core.config.sqlite_bootstrap import bootstrap_database, shipped_released_version

    bootstrap_database(
        tmp_path / "home" / "state" / "studio.db", target_version=shipped_released_version()
    )
    authority = _doctor(tmp_path)["checks"]["authority_data"]
    assert authority["warnings"] == []
    assert any("zero rows" in n for n in authority["notes"])


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


@pytest.fixture(scope="module")
def installed_pending(tmp_path_factory) -> Path:
    """An INSTALLED home (installed-version and an integration manifest) whose closed
    authority has no -wal/-shm and is one RELEASED migration behind: the state of an
    operator's home right after a self-install brought a new migration, before any
    command migrated it."""
    tmp = tmp_path_factory.mktemp("doctor-installed")
    for sub in ("home", "claude", "userhome", "work"):
        (tmp / sub).mkdir()
    from core.config.sqlite_bootstrap import bootstrap_database, shipped_released_version

    db = tmp / "home" / "state" / "studio.db"
    released = shipped_released_version()
    bootstrap_database(db, target_version=released - 1)
    conn = sqlite3.connect(str(db))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal", "a live authority is WAL"
    conn.close()  # the last connection closing cleanly removes the sidecars
    for suffix in ("-wal", "-shm"):
        assert not Path(str(db) + suffix).exists()
    (tmp / "home" / "state" / "installed-version").write_text(
        "0.1.0 " + "a" * 40 + "\n", encoding="utf-8"
    )
    manifest = tmp / "home" / "integrations" / "claude_code" / "roots" / "x" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    return tmp


def test_an_installed_homes_doctor_writes_nothing_with_a_migration_pending(installed_pending):
    roots = (
        installed_pending / "home",
        installed_pending / "claude",
        installed_pending / "userhome",
    )
    before = _snapshot(*roots)
    proc = _ds(installed_pending, "doctor")
    after = _snapshot(*roots)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not changed, f"ds doctor wrote: {changed}\n{proc.stdout[-1500:]}{proc.stderr[-1500:]}"
