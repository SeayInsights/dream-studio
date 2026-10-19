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
    # An authority the migrations have run on: the guard refuses a schema-less one.
    conn.execute("CREATE TABLE _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute("INSERT INTO _schema_version VALUES (1, '2026-10-01')")
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

    monkeypatch.setattr(si, "_build_app_real", si._build_app, raising=False)
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
    assert (
        result["ok"] is False
        and f"ds --home {home.resolve()} restore <dir> --execute" in result["error"]
    )
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
    real _build_app. Here only the slow commands are stubbed -- the
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
    """`ds self-install` re-baselined over a drop and reported ok."""
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


def _checkout_launcher(home: Path) -> Path:
    """What `ds install-command` from a checkout leaves first on PATH (~/.local/bin):
    pinned to *home* with DREAM_STUDIO_HOME, as the real launcher template does."""
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    launcher = local_bin / ("ds.cmd" if os.name == "nt" else "ds")
    launcher.write_text(
        '@echo off\nset "DREAM_STUDIO_SOURCE_ROOT=C:\\src\\dream-studio"\n'
        f'set "DREAM_STUDIO_HOME={home}"\n'
        'py "C:\\src\\dream-studio\\interfaces\\cli\\ds.py" %*\n',
        encoding="utf-8",
    )
    return launcher


def test_a_launcher_pinned_to_another_home_is_reported_and_left(
    si, repo, home, fake_build, tmp_path, monkeypatch
):
    """Repointing a ~/.local/bin launcher pinned to a DIFFERENT home sent that home's
    operator to this home's app and authority."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "userhome"))
    other = _checkout_launcher(tmp_path / "other-home")
    before = other.read_text(encoding="utf-8")
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")

    dry = si.self_install(plan, dry_run=True)
    assert not any(w["step"] == "repoint-launcher" for w in dry["writes"])
    result = si.self_install(plan, dry_run=False)
    assert result["ok"], result
    assert other.read_text(encoding="utf-8") == before
    assert [item["path"] for item in result["left_launchers"]] == [str(other)]


def test_a_repointed_launcher_is_saved_and_kept_delegating_on_rollback(
    si, repo, home, fake_build, tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "userhome"))
    _authority(home)
    first = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    assert si.self_install(first, dry_run=False)["ok"]

    stale = _checkout_launcher(home)
    before = stale.read_text(encoding="utf-8")
    (repo / "module.py").write_text("COMMITTED = 2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two")
    second = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    result = si.self_install(second, dry_run=False)
    assert result["ok"], result
    saved = Path(result["repointed_launchers"][0]["saved"])
    assert saved.is_file() and saved.read_text(encoding="utf-8") == before
    assert str(si.launcher_path(home)) in stale.read_text(encoding="utf-8")

    # A rollback goes to another INSTALLED app: putting the checkout launcher back would
    # take PATH off the app the rollback just made current.
    dry = si.rollback(home, dry_run=True)
    assert not any(w["step"] == "restore-launcher" for w in dry["writes"])
    back = si.rollback(home, dry_run=False)
    assert back["ok"], back
    assert str(si.launcher_path(home)) in stale.read_text(encoding="utf-8")
    assert [item["saved"] for item in back["saved_launchers"]] == [str(saved)]
    assert saved.read_text(encoding="utf-8") == before


def test_rollback_with_no_previous_says_why_and_what_to_do(si, home):
    result = si.rollback(home, dry_run=True)
    assert not result["ok"]
    assert "self-install" in result["error"] and "--execute" in result["error"]
    assert "--repo" in result["error"], "the installed ds needs --repo to name a checkout"


def test_checkout_install_command_into_an_app_home_writes_delegating_launchers(tmp_path):
    """From a checkout, `ds install-command --execute` against a home with an installed
    app rewrote ~/.local/bin back to the checkout."""
    from core import installed_productization_setup as setup
    from core.config import paths

    home = tmp_path / "home"
    (home / "app" / "current").mkdir(parents=True)
    result = setup.install_global_command_surface(
        source_root=paths.code_root(),
        dream_studio_home=home,
        command_dir=tmp_path / "bin",
        execute=True,
    )
    assert result["written"]
    for name in result["launchers"]:
        text = (tmp_path / "bin" / name).read_text(encoding="utf-8")
        assert str(home / "bin") in text, name
        assert "DREAM_STUDIO_SOURCE_ROOT" not in text and "interfaces" not in text, name


def test_self_install_repoints_a_checkout_launcher_on_path(
    si, repo, home, fake_build, tmp_path, monkeypatch
):
    """~/.local/bin/ds.cmd stayed first on PATH and kept running the
    checkout after self-install; the app's launcher was never reached."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "userhome"))
    stale = _checkout_launcher(home)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")

    dry = si.self_install(plan, dry_run=True)
    assert any(w["step"] == "repoint-launcher" and w["path"] == str(stale) for w in dry["writes"])
    assert "DREAM_STUDIO_SOURCE_ROOT" in stale.read_text(encoding="utf-8")

    result = si.self_install(plan, dry_run=False)
    assert result["ok"], result
    text = stale.read_text(encoding="utf-8")
    assert str(si.launcher_path(plan.home)) in text
    assert "DREAM_STUDIO_SOURCE_ROOT" not in text


def test_install_command_from_an_app_delegates_to_the_home_launcher(tmp_path, monkeypatch):
    """Run from an installed app, `ds install-command` pinned one concrete venv; it must
    go through <home>/bin, which `current` keeps pointing at the live app."""
    from core import installed_productization_setup as setup
    from core.config import paths

    monkeypatch.setattr(paths, "is_source_checkout", lambda root=None: False)
    home = tmp_path / "home"
    result = setup.install_global_command_surface(
        source_root=paths.code_root(),
        dream_studio_home=home,
        command_dir=tmp_path / "bin",
        execute=True,
    )
    for name in result["launchers"]:
        text = (tmp_path / "bin" / name).read_text(encoding="utf-8")
        assert str(home / "bin") in text, name
        assert "interfaces" not in text and "venv" not in text, name


# --- activation carried over --------------------------------------------------------


def test_an_authority_activated_in_the_old_tree_keeps_its_activation(tmp_path, monkeypatch):
    """The operator activated 159 by bumping the in-tree .released_version
    (the old mechanism). After self-install the shipped sentinel says 158 and no
    migrations-activated-version exists, so `ds migrate status` reported 159 pending on an
    authority that already had it."""
    from core.config import sqlite_bootstrap as sb

    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    db = tmp_path / "home" / "state" / "studio.db"
    sb.bootstrap_database(db)
    applied = sb.latest_migration_version()
    monkeypatch.setattr(sb, "shipped_released_version", lambda: applied - 1)

    assert sb.pending_migrations_info(db)
    assert sb.carry_over_activation(db) == applied
    assert sb.pending_migrations_info(db) == []
    assert sb.carry_over_activation(db) is None, "an existing record is never rewritten"


def test_self_install_runs_the_carry_over_with_the_new_app(si):
    assert "carry_over_activation" in si._MIGRATE_PROBE


# --- a dry run that matches the real run ---------------------------------------------


def test_dry_run_reports_the_guard_refusal_the_real_run_would_hit(si, repo, home):
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    result = si.self_install(plan, dry_run=True)
    assert result["ok"] is False
    assert "Refusing" in result["error"]
    assert "never creates" in result["error"]
    assert not any(w["step"] == "migrate-authority" for w in result.get("writes", []))


def test_first_install_dry_run_has_no_previous_and_says_it_creates_the_authority(si, repo, home):
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    steps = {w["step"]: w for w in si.self_install(plan, dry_run=True)["writes"]}
    assert "record-previous" not in steps
    assert "creates it" in steps["migrate-authority"]["detail"]


def test_dry_run_lists_each_roots_integration_plan(si, repo, home, tmp_path):
    root = tmp_path / "claude-root"
    root.mkdir()
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD", config_roots=[root])
    integrate = [
        w for w in si.self_install(plan, dry_run=True)["writes"] if w["step"] == "integrate"
    ]
    assert len(integrate) == 1
    detail = integrate[0]
    assert detail["settings"] == str(root / "settings.json")
    assert detail["manifest"].endswith("manifest.json")
    assert set(detail["operations"]) >= {"create", "merge_json"}
    assert all(" -I -X utf8 -m " in c for c in detail["hook_commands"])


def test_dry_run_lists_the_pre_migration_backup(si, repo, home):
    mig = repo / "core" / "event_store" / "migrations"
    mig.mkdir(parents=True)
    (mig / "001_a.sql").write_text("CREATE TABLE a (x);\n", encoding="utf-8")
    (mig / "002_b.sql").write_text("CREATE TABLE b (x);\n", encoding="utf-8")
    (mig / ".released_version").write_text("2", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "migrations")
    db = home / "state" / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute("INSERT INTO _schema_version VALUES (1, 'x')")
    conn.commit()
    conn.close()
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    steps = [
        w
        for w in si.self_install(plan, dry_run=True)["writes"]
        if w["step"] == "pre-migration-backup"
    ]
    assert len(steps) == 1 and "studio-pre-2-" in steps[0]["path"]


def test_dry_run_refuses_over_a_drop_like_the_real_run(si, repo, home):
    """A dry run said ok:true over a recorded drop the real run then refused."""
    db = _authority(home, rows=3)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE business_projects (project_id TEXT, name TEXT)")
    conn.execute("INSERT INTO business_projects VALUES ('p1', 'a')")
    conn.commit()
    conn.close()
    (home / "state" / "authority-counts.json").write_text(
        json.dumps({"recorded_at": "2026-10-15T00:00:00+00:00", "counts": {"projects": 5}}),
        encoding="utf-8",
    )
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    dry = si.self_install(plan, dry_run=True)
    assert dry["ok"] is False and "dropped" in dry["error"]


def test_dry_run_refuses_a_live_app_with_no_record_like_the_real_run(si, repo, home, fake_build):
    """With app/current pointing at the app being installed and its app.json missing,
    the dry run planned create-venv while the real run refused."""
    _authority(home)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    assert si.self_install(plan, dry_run=False)["ok"]
    (plan.app_dir / si.APP_RECORD).unlink()

    dry = si.self_install(plan, dry_run=True)
    real = si.self_install(plan, dry_run=False)
    assert dry["ok"] is False and real["ok"] is False
    assert "live app" in dry["error"] and "live app" in real["error"]
    assert "--ref" in dry["error"], "the advice must not dead-end on a rollback"
    assert "--repo" in dry["error"]


def test_dry_run_lists_the_activation_carry_over_and_the_integration_backups(
    si, repo, home, tmp_path
):
    mig = repo / "core" / "event_store" / "migrations"
    mig.mkdir(parents=True)
    for n in (1, 2, 3):
        (mig / f"00{n}_m.sql").write_text(f"CREATE TABLE t{n} (x);\n", encoding="utf-8")
    (mig / ".released_version").write_text("2", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "migrations")
    db = home / "state" / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.executemany("INSERT INTO _schema_version VALUES (?, 'x')", [(1,), (2,), (3,)])
    conn.commit()
    conn.close()
    root = tmp_path / "claude-root"
    root.mkdir()
    (root / "settings.json").write_text("{}", encoding="utf-8")

    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD", config_roots=[root])
    writes = si.self_install(plan, dry_run=True)["writes"]
    carry = [w for w in writes if w["step"] == "carry-over-activation"]
    assert carry and carry[0]["path"] == str(home / "state" / "migrations-activated-version")
    assert carry[0]["content"] == "3"
    integrate = [w for w in writes if w["step"] == "integrate"][0]
    backups = integrate["backups"]
    assert any(b.startswith(str(home / "backups" / "claude_code")) for b in backups), backups
    assert any("settings.json" in b for b in backups)


def test_the_app_environment_keeps_a_scoped_create_authority(si, home, monkeypatch):
    db = home / "state" / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_CREATE_AUTHORITY", str(db))
    assert si._app_env(home)["DREAM_STUDIO_CREATE_AUTHORITY"] == str(db)
    monkeypatch.setenv("DREAM_STUDIO_CREATE_AUTHORITY", "1")
    assert "DREAM_STUDIO_CREATE_AUTHORITY" not in si._app_env(home)


# --- nits ------------------------------------------------------------------------------


def test_cli_requires_execute_or_dry_run(repo, home):
    proc = _cli(home, "--repo", str(repo))
    assert proc.returncode == 1
    assert "--execute" in json.loads(proc.stdout)["error"]


def test_rollback_refuses_a_previous_that_is_not_a_bare_app_id(si, home):
    (home / "app").mkdir()
    (home / "app" / "previous").write_text("..\\..\\elsewhere\n", encoding="utf-8")
    result = si.rollback(home, dry_run=True)
    assert result["ok"] is False and "app id" in result["error"]


def test_an_incomplete_live_app_is_never_removed(si, repo, home, fake_build, monkeypatch):
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    assert si.self_install(plan, dry_run=False)["ok"]
    (plan.app_dir / si.APP_RECORD).unlink()  # the live app now looks incomplete
    monkeypatch.setattr(si, "_build_app", si.__dict__["_build_app_real"])
    result = si.self_install(plan, dry_run=False)
    assert result["ok"] is False and "live" in result["error"]
    assert si.venv_python(plan.app_dir / "venv").is_file()


def test_a_failed_command_shows_its_arguments_not_its_program(si):
    shown = si._shown(["C:/py.exe", "-I", "-c", "import x\nprint(1)", "C:/home/state/studio.db"])
    assert shown == "C:/py.exe -I -c <inline program> C:/home/state/studio.db"


def test_self_install_refuses_an_installed_homes_empty_authority_with_no_baseline(
    si, repo, home, fake_build, monkeypatch
):
    """It printed doctor's replaced-authority warning inside ok:true and recorded a zero
    baseline, so the next doctor said pass over what may be a replaced authority."""
    from core.config.sqlite_bootstrap import CREATE_AUTHORITY_ENV, bootstrap_database

    (home / "state" / "installed-version").write_text("0.1.0 " + "a" * 40 + "\n", "utf-8")
    db = home / "state" / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    monkeypatch.setenv(CREATE_AUTHORITY_ENV, str(db))
    bootstrap_database(db)
    monkeypatch.delenv(CREATE_AUTHORITY_ENV)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    for dry_run in (True, False):
        result = si.self_install(plan, dry_run=dry_run)
        assert result["ok"] is False, result
        assert "doctor --record-counts" in result["error"]
    assert not (home / "state" / "authority-counts.json").exists()
    assert not (home / "app" / "current").exists()


def test_a_first_install_that_creates_the_authority_records_it_silently(si, repo, home, fake_build):
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    result = si.self_install(plan, dry_run=False)
    assert result["ok"], result


def test_the_integration_preview_lists_only_what_will_change(si, repo, home, tmp_path):
    """Over an installed root the dry run planned 652 backups and 650 writes; the real
    install wrote 5 and 0. It now counts only the files whose content will change."""
    from unittest.mock import patch

    from integrations.installer.claude_code import ClaudeCodeInstaller

    _authority(home)
    root = tmp_path / "claude-root"
    root.mkdir()
    with patch("integrations.installer.claude_code_launcher._write_path_to_profile") as prof:
        prof.return_value = {"profile": "x", "action": "skipped"}
        ClaudeCodeInstaller(root, "user", ds_home=home, hook_mode="module").install("execute")
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD", config_roots=[root])
    result = si.self_install(plan, dry_run=True)
    assert result["ok"], result
    preview = [w for w in result["writes"] if w["step"] == "integrate"][0]
    # The installed hook interpreter differs (the new app's), so settings.json may change.
    assert sum(preview["operations"].values()) <= 3, preview["operations"]
    assert len(preview["backups"]) <= 3, preview["backups"][:5]
    assert preview["unchanged"] > 100


def _backup_dir(root: Path, name: str, age: int) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "studio.db").write_bytes(b"x" * 10)
    stamp = 1_700_000_000 + age
    os.utime(d / "studio.db", (stamp, stamp))
    os.utime(d, (stamp, stamp))
    return d


def test_backup_retention_keeps_the_newest_five_and_nothing_else_is_touched(si, home):
    """Each install and rollback keeps a full copy of the authority (about 1.5 GB at real
    size) and nothing ever removed one."""
    backups = home / "state" / "backups"
    made = [_backup_dir(backups, f"self-install-9.9.9-aaaaaaaaaa-{i:02d}", i) for i in range(6)]
    made += [_backup_dir(backups, "self-install-rollback-9.9.9-bbbbbbbbbb-x", 10)]
    keep = [backups / "studio-pre-restore-20261016T161346Z.db", backups / "studio-pre-3-x.db"]
    for f in keep:
        f.write_bytes(b"y")
    manual = _backup_dir(home / "backups", "manual", 0)

    removed = si.prune_self_install_backups(home, keep=5)
    assert sorted(Path(p).name for p in removed) == [
        "self-install-9.9.9-aaaaaaaaaa-00",
        "self-install-9.9.9-aaaaaaaaaa-01",
    ]
    survivors = sorted(p.name for p in backups.iterdir())
    assert "self-install-rollback-9.9.9-bbbbbbbbbb-x" in survivors
    assert all(f.exists() for f in keep) and manual.exists()


def test_a_self_install_reports_the_backups_it_pruned(si, repo, home, fake_build):
    _authority(home)
    backups = home / "state" / "backups"
    for i in range(6):
        _backup_dir(backups, f"self-install-0.0.1-cccccccccc-{i:02d}", i)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    dry = si.self_install(plan, dry_run=True)
    assert any(w["step"] == "prune-backup" for w in dry["writes"])
    result = si.self_install(plan, dry_run=False)
    assert result["ok"], result
    assert result["pruned_backups"], result
    assert len([p for p in backups.iterdir() if p.name.startswith("self-install-")]) == 5


def _commit(repo: Path, n: int) -> None:
    (repo / "module.py").write_text(f"COMMITTED = {n}\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", f"commit {n}")


def test_a_saved_checkout_launcher_outlives_backup_retention(
    si, repo, home, fake_build, tmp_path, monkeypatch
):
    """The copy of a repointed checkout launcher was written inside that install's
    self-install-* backup, which retention removes five installs later, while rollback
    went on reporting it at the deleted path."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "userhome"))
    _authority(home)
    assert si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)["ok"]
    stale = _checkout_launcher(home)
    before = stale.read_text(encoding="utf-8")
    _commit(repo, 2)
    result = si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)
    assert result["ok"], result
    saved = Path(result["repointed_launchers"][0]["saved"])
    for n in range(3, 8):
        _commit(repo, n)
        more = si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)
        assert more["ok"], more
    assert more["pruned_backups"], "five more installs must have pruned something"

    back = si.rollback(home, dry_run=False)
    assert back["ok"], back
    reported = [Path(item["saved"]) for item in back["saved_launchers"]]
    assert reported == [saved]
    assert saved.is_file(), f"rollback reports {saved}, which retention deleted"
    assert saved.read_text(encoding="utf-8") == before


def test_retention_never_prunes_a_backup_the_launcher_record_cites(si, home):
    """A home installed before the launcher copies moved out keeps them inside a
    self-install-* backup; that backup is kept while the record points into it."""
    backups = home / "state" / "backups"
    cited = _backup_dir(backups, "self-install-9.9.9-aaaaaaaaaa-old", 0)
    (cited / "launchers").mkdir()
    (cited / "launchers" / "ds.cmd").write_text("old launcher", encoding="utf-8")
    for i in range(1, 7):
        _backup_dir(backups, f"self-install-9.9.9-aaaaaaaaaa-{i:02d}", i)
    (home / "state" / si.REPOINTED_RECORD).write_text(
        json.dumps({"launchers": [{"path": "x", "saved": str(cited / "launchers" / "ds.cmd")}]}),
        encoding="utf-8",
    )
    removed = si.prune_self_install_backups(home, keep=5)
    assert str(cited) not in removed
    assert (cited / "launchers" / "ds.cmd").is_file()
    assert [Path(p).name for p in removed] == ["self-install-9.9.9-aaaaaaaaaa-01"]


def test_rollback_dry_run_lists_the_backups_the_rollback_prunes(si, repo, home, fake_build):
    _authority(home)
    assert si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)["ok"]
    _commit(repo, 2)
    assert si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)["ok"]
    backups = home / "state" / "backups"
    for i in range(6):
        _backup_dir(backups, f"self-install-0.0.1-cccccccccc-{i:02d}", i)

    dry = si.rollback(home, dry_run=True)
    listed = sorted(w["path"] for w in dry["writes"] if w["step"] == "prune-backup")
    assert listed, dry["writes"]
    back = si.rollback(home, dry_run=False)
    assert back["ok"], back
    assert listed == sorted(back["pruned_backups"])


def test_rollbacks_in_one_second_each_take_their_own_backup(
    si, repo, home, fake_build, monkeypatch
):
    """Two rollbacks in one second named the same backup directory, and VACUUM INTO
    refused the second: "output file already exists"."""

    class Frozen(si.datetime):
        @classmethod
        def now(cls, tz=None):
            return si.datetime(2026, 10, 19, 12, 0, 0, 123456, tzinfo=tz)

    _authority(home)
    assert si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)["ok"]
    _commit(repo, 2)
    assert si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)["ok"]
    monkeypatch.setattr(si, "datetime", Frozen)
    backups = []
    for _ in range(3):
        back = si.rollback(home, dry_run=False)
        assert back["ok"], back
        backups.append(back["backup"])
    assert len(set(backups)) == 3, backups
    assert all(Path(b).is_file() for b in backups)


def test_dry_run_lists_the_repointed_launchers_record(
    si, repo, home, fake_build, tmp_path, monkeypatch
):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "userhome"))
    _authority(home)
    assert si.self_install(si.resolve_plan(home=home, repo=repo, ref="HEAD"), dry_run=False)["ok"]
    _checkout_launcher(home)
    _commit(repo, 2)
    plan = si.resolve_plan(home=home, repo=repo, ref="HEAD")
    dry = si.self_install(plan, dry_run=True)
    record = str(home / "state" / si.REPOINTED_RECORD)
    assert record in [w["path"] for w in dry["writes"]], [w["path"] for w in dry["writes"]]
    saved = [w for w in dry["writes"] if w["step"] == "repoint-launcher"]
    assert saved and all("state" in w["detail"] for w in saved)
    result = si.self_install(plan, dry_run=False)
    assert result["ok"], result
    assert Path(record).is_file()
    assert all(item["saved"] in saved[0]["detail"] for item in result["repointed_launchers"])
