"""`ds self-install`: build from a commit, switch only after everything else worked.

The slow parts (building a wheel and installing its dependencies into a venv) are
replaced by a fake app so these run in seconds; tests/unit/test_wheel_runs_without_
checkout.py covers the real build, and the operator evidence is a real self-install
into a scratch home. What is exercised for real here: the git source checks, the
export, the dry-run plan, the authority backup, the switch of <home>/app/current (a
junction on Windows), installed-version, the launcher, and rollback.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def si():
    """core.self_install (imported per test, so a missing module fails
    each test rather than the whole file's collection)."""
    import importlib

    return importlib.import_module("core.self_install")


GIT = [
    "git",
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "core.autocrlf=false",
]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [*GIT, "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    (repo / "module.py").write_text("COMMITTED = True\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "one")
    return repo


@pytest.fixture
def home(tmp_path) -> Path:
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    return home


def _authority(home: Path, rows: int = 3) -> Path:
    db = home / "state" / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE demo_rows (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO demo_rows(name) VALUES (?)", [(f"p{i}",) for i in range(rows)])
    conn.commit()
    conn.close()
    return db


def _snapshot(root: Path) -> dict[str, str]:
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = Path(dirpath) / name
            out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture
def fake_build(si, monkeypatch):
    """Replace the wheel build + venv install with a complete-looking fake app, and the
    calls into the new app with canned answers. Returns the list of commands run."""
    calls: list[list[str]] = []

    def build(plan, log):
        venv = plan.app_dir / "venv"
        si.venv_python(venv).parent.mkdir(parents=True)
        si.venv_python(venv).write_text("", encoding="utf-8")
        si.venv_ds(venv).write_text("", encoding="utf-8")
        (venv / si.APP_HOME_MARKER).write_text(str(plan.home), encoding="utf-8")
        (plan.app_dir / si.APP_RECORD).write_text(
            json.dumps({"app_id": plan.app_id, "version": plan.version, "sha": plan.sha}),
            encoding="utf-8",
        )

    def run(cmd, *, env=None, cwd=None):
        calls.append(cmd)
        if "-c" in cmd:
            return json.dumps({"schema_version": 159, "latest": 159, "code_root": "x"})
        return "ok"

    monkeypatch.setattr(si, "_build_app", build)
    monkeypatch.setattr(si, "_run", run)
    return calls


def test_refuses_a_dirty_tree(si, repo, home):
    (repo / "module.py").write_text("COMMITTED = False\n", encoding="utf-8")
    with pytest.raises(si.SelfInstallError, match="dirty tree"):
        si.resolve_plan(home=home, repo=repo, ref="HEAD")


def test_untracked_files_do_not_make_the_tree_dirty(si, repo, home):
    (repo / "scratch.txt").write_text("not in any commit", encoding="utf-8")
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    assert plan.version == "9.9.9" and len(plan.sha) == 40


def test_export_is_the_commit_never_the_working_tree(si, repo, tmp_path):
    sha = _git(repo, "rev-parse", "HEAD")
    (repo / "module.py").write_text("COMMITTED = False\n", encoding="utf-8")
    (repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    dest = tmp_path / "export"
    dest.mkdir()
    si.export_commit(repo, sha, dest, tmp_path / "a.zip")
    assert (dest / "module.py").read_text(encoding="utf-8") == "COMMITTED = True\n"
    assert not (dest / "untracked.py").exists()


def test_dry_run_prints_every_write_and_writes_nothing(si, repo, home):
    _authority(home)
    before = _snapshot(home)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD", config_roots=[home / "cfg"])

    result = si.self_install(plan, dry_run=True)

    assert _snapshot(home) == before
    assert not (home / "app").exists()
    steps = {w["step"]: w for w in result["writes"]}
    for step in (
        "export",
        "build-wheel",
        "create-venv",
        "install",
        "backup-authority",
        "migrate-authority",
        "switch-current",
        "installed-version",
        "launcher",
        "integrate",
    ):
        assert step in steps, step
    assert steps["installed-version"]["content"] == f"9.9.9 {plan.sha}"
    # Built where it lives: a venv is not relocatable (console scripts embed its path).
    assert steps["create-venv"]["path"] == str(plan.app_dir / "venv")
    assert "finalize" not in steps
    assert f'--home "{home.resolve()}"' in steps["launcher"]["content"]
    assert str(home.resolve() / "app" / "current" / "venv") in steps["launcher"]["content"]
    assert "pre-push" not in json.dumps(result)


def test_a_failed_migration_switches_nothing(si, repo, home, fake_build, monkeypatch):
    _authority(home)
    (home / "state" / "installed-version").write_text("0.0.1 oldsha\n", encoding="utf-8")

    def failing_run(cmd, *, env=None, cwd=None):
        if "-c" in cmd:
            raise si.SelfInstallError("migration 160 failed")
        return "ok"

    monkeypatch.setattr(si, "_run", failing_run)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    result = si.self_install(plan, dry_run=False)

    assert result["ok"] is False and result["switched"] is False
    assert "migration 160 failed" in result["error"]
    assert not (home / "app" / "current").exists()
    assert (home / "state" / "installed-version").read_text(encoding="utf-8") == "0.0.1 oldsha\n"
    assert not si.launcher_path(home).exists()


def test_install_switches_records_and_rolls_back(si, repo, home, fake_build):
    db = _authority(home)
    first = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    r1 = si.self_install(first, dry_run=False)
    assert r1["ok"] and r1["switched"]

    # The backup is a consistent copy, restorable with `ds restore <dir> --execute`.
    backup = Path(r1["backup"])
    assert backup.name == "studio.db" and backup.parent.parent == home / "state" / "backups"
    copy = sqlite3.connect(backup)
    assert copy.execute("SELECT COUNT(*) FROM demo_rows").fetchone()[0] == 3
    copy.close()
    assert db.is_file()

    (repo / "module.py").write_text("COMMITTED = 2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two")
    second = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    r2 = si.self_install(second, dry_run=False)
    assert r2["ok"] and r2["current_before"] == first.app_id

    app_root = home / "app"
    assert (app_root / "current").resolve() == (app_root / second.app_id).resolve()
    assert (app_root / "previous").read_text(encoding="utf-8").strip() == first.app_id
    assert (home / "state" / "installed-version").read_text(encoding="utf-8").split() == [
        "9.9.9",
        second.sha,
    ]
    launcher = si.launcher_path(home).read_text(encoding="utf-8")
    assert f'--home "{home.resolve()}"' in launcher
    assert "app" in launcher and "current" in launcher
    assert len(list((home / "bin").iterdir())) == 1, "exactly one launcher"

    dry = si.rollback(home, dry_run=True)
    assert dry["ok"] and dry["rollback_to"] == first.app_id
    assert (app_root / "current").resolve() == (app_root / second.app_id).resolve()

    back = si.rollback(home, dry_run=False)
    assert back["ok"], back
    assert (app_root / "current").resolve() == (app_root / first.app_id).resolve()
    assert (app_root / "previous").read_text(encoding="utf-8").strip() == second.app_id
    assert (home / "state" / "installed-version").read_text(encoding="utf-8").split()[1] == (
        first.sha
    )
    # Switching `current` never touched what it pointed at.
    assert si.venv_python(app_root / second.app_id / "venv").is_file()


def test_rollback_refuses_when_the_previous_app_cannot_open_the_authority(
    si, repo, home, fake_build, monkeypatch
):
    _authority(home)
    si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)
    (repo / "module.py").write_text("COMMITTED = 3\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "three")
    si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)
    current = (home / "app" / "current").resolve()

    monkeypatch.setattr(
        si,
        "_run",
        lambda cmd, *, env=None, cwd=None: json.dumps({"schema_version": 160, "latest": 159}),
    )
    result = si.rollback(home, dry_run=False)
    assert result["ok"] is False and "ds restore" in result["error"]
    assert (home / "app" / "current").resolve() == current


def _cli(home: Path, *args: str) -> subprocess.CompletedProcess:
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith("DREAM_STUDIO")}
    env.pop("DS_DREAM_STUDIO_HOME", None)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(home), "self-install", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=home.parent,
        env=env,
        timeout=600,
    )


def test_cli_dry_run_against_a_scratch_home_writes_nothing(repo, home):
    before = _snapshot(home)
    proc = _cli(home, "--repo", str(repo), "--dry-run")
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout)
    assert result["dry_run"] is True and result["version"] == "9.9.9"
    assert [w["step"] for w in result["writes"]][-2:] == ["launcher", "record-counts"]
    assert _snapshot(home) == before and not (home / "app").exists()


def test_cli_refuses_a_dirty_tree(repo, home):
    (repo / "VERSION").write_text("9.9.10\n", encoding="utf-8")
    proc = _cli(home, "--repo", str(repo), "--dry-run")
    assert proc.returncode == 1
    assert "dirty tree" in json.loads(proc.stdout)["error"]


def test_the_real_build_writes_the_home_marker_into_the_app_venv(si, repo, home, monkeypatch):
    """The fake_build fixture writes the marker itself, so it proved nothing about the
    real _build_app (round-table S14). Here only the slow commands are stubbed -- the
    wheel build, the venv and the pip install -- and the marker must come from the code."""
    import sys as _sys

    def run(cmd, *, env=None, cwd=None):
        if "wheel" in cmd and "-w" in cmd:
            dist = Path(cmd[cmd.index("-w") + 1])
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "dream_studio-9.9.9-py3-none-any.whl").write_bytes(b"")
        elif cmd[1:3] == ["-m", "venv"]:
            py = si.venv_python(Path(cmd[3]))
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("", encoding="utf-8")
        return ""

    monkeypatch.setattr(si, "_run", run)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    si._build_app(plan, [])
    marker = plan.app_dir / "venv" / si.APP_HOME_MARKER
    assert marker.read_text(encoding="utf-8").strip() == str(plan.home)
    assert si.app_record(plan.app_dir)["sha"] == plan.sha
    assert _sys.executable  # the build ran with this interpreter's pip


def test_self_install_refuses_over_a_drop_and_keeps_the_baseline(si, repo, home, fake_build):
    """Round-table S4: self-install re-baselined over a drop and reported ok."""
    db = _authority(home, rows=3)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE business_projects (project_id TEXT, name TEXT)")
    conn.executemany("INSERT INTO business_projects VALUES (?, ?)", [("p1", "a"), ("p2", "b")])
    conn.commit()
    conn.close()
    first = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    baseline = home / "state" / "authority-counts.json"
    baseline.write_text(
        json.dumps({"recorded_at": "2026-10-15T00:00:00+00:00", "counts": {"projects": 5}}),
        encoding="utf-8",
    )
    result = si.self_install(first, dry_run=False)
    assert result["ok"] is False and result["switched"] is False
    assert "dropped" in result["error"]
    assert json.loads(baseline.read_text(encoding="utf-8"))["counts"]["projects"] == 5
    assert not (home / "app" / "current").exists()
