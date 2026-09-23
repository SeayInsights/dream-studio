"""`--home` means home for everything a command writes; telemetry needs a real install.

Measured 2026-09-23 with Dream Studio uninstalled: `ds --home <scratch> work-order create`
reported ok:true, wrote its event into the DEFAULT spool, created a default studio.db, and
left the --home authority with zero rows. The pre-push telemetry guard -- "emit if
~/.dream-studio exists" -- then saw that resurrected directory and wrote 514 gate events
into a home the operator had removed.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-09-23T00:00:00+00:00"


def _authority(home: Path) -> Path:
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at,"
        " updated_at) VALUES ('p', 'P', '', 'active', ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones (milestone_id, project_id, title, status,"
        " created_at, updated_at) VALUES ('m', 'p', 'M', 'active', ?, ?)",
        (NOW, NOW),
    )
    conn.commit()
    conn.close()
    return db


def test_a_mutation_under_home_writes_nothing_to_the_default_home(tmp_path):
    """The measured defect, end to end through the real CLI in a subprocess: the default
    home is pointed at a scratch directory, so a leak is visible without touching the
    operator's."""
    fake_user = tmp_path / "user"
    fake_user.mkdir()
    home = tmp_path / "home"
    db = _authority(home)

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DREAM_STUDIO_HOME", "DS_SPOOL_ROOT", "DREAM_STUDIO_DB_PATH")
    }
    env["USERPROFILE"] = str(fake_user)
    env["HOME"] = str(fake_user)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "interfaces.cli.ds",
            "--home",
            str(home),
            "work-order",
            "create",
            "p",
            "--milestone",
            "m",
            "--title",
            "probe",
            "--description",
            "A probe work order proving where the writes land when only --home is given.",
            "--type",
            "infrastructure",
            "--module-boundary",
            "core/x",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    assert result.returncode == 0, result.stdout[-600:] + result.stderr[-600:]

    leaked = [p for p in fake_user.rglob("*") if p.is_file()]
    assert leaked == [], f"--home leaked into the default home: {leaked[:5]}"

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT count(*) FROM business_work_orders WHERE title = 'probe'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert rows == 1, "the work order did not land in the --home authority"


def test_pre_push_telemetry_needs_an_install_not_a_directory(tmp_path, monkeypatch):
    """A directory any stray write can create is not an install: the guard let 514 gate
    events into one. Only the installer writes config/runtime.json."""
    from core.gates import pre_push

    monkeypatch.delenv("DS_SPOOL_ROOT", raising=False)
    home = tmp_path / ".dream-studio"
    (home / "events").mkdir(parents=True)  # what a stray write leaves behind
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    assert pre_push._telemetry_home_exists() is False

    (home / "config").mkdir()
    (home / "config" / "runtime.json").write_text("{}", encoding="utf-8")
    assert pre_push._telemetry_home_exists() is True


def test_the_home_export_ends_with_the_command(tmp_path, monkeypatch):
    """An in-process caller must not inherit it: the test suite calls `ds main` in-process,
    and a permanent export would steer every later test's events into a deleted tmp dir."""
    from interfaces.cli import ds

    for key in ("DREAM_STUDIO_HOME", "DS_SPOOL_ROOT", "DREAM_STUDIO_DB_PATH"):
        monkeypatch.delenv(key, raising=False)
    seen = {}

    def spy(parser, args, source_root, home):
        seen.update({k: os.environ.get(k) for k in ("DREAM_STUDIO_HOME", "DS_SPOOL_ROOT")})
        return 0

    monkeypatch.setattr(ds, "_run", spy)
    home = tmp_path / "home"
    assert ds.main(["--home", str(home), "version"]) == 0
    assert seen["DS_SPOOL_ROOT"] == str(home.resolve() / "events"), "not set during the command"
    assert "DS_SPOOL_ROOT" not in os.environ, "the export outlived the command"


def test_the_flag_wins_over_an_inherited_home_and_gives_it_back(tmp_path, monkeypatch):
    """The runtime-check image sets DREAM_STUDIO_HOME itself. When --home only filled in
    unset variables it never took effect there, and analytics landed in the image's home.
    The inherited value is restored once the command returns."""
    from interfaces.cli import ds

    decoy = tmp_path / "inherited"
    inherited = {
        "DREAM_STUDIO_HOME": str(decoy),
        # Round 2: `ds render` read this alternate name first, and --home did not set it.
        "DS_DREAM_STUDIO_HOME": str(decoy),
        "DS_HOME": str(decoy),
        "DS_SPOOL_ROOT": str(decoy / "events"),
        "DREAM_STUDIO_DB_PATH": str(decoy / "state" / "studio.db"),
    }
    for key, value in inherited.items():
        monkeypatch.setenv(key, value)
    seen = {}

    def spy(parser, args, source_root, home):
        seen.update({k: os.environ.get(k) for k in inherited})
        return 0

    monkeypatch.setattr(ds, "_run", spy)
    home = (tmp_path / "home").resolve()
    assert ds.main(["--home", str(home), "version"]) == 0
    assert seen == {
        "DREAM_STUDIO_HOME": str(home),
        "DS_DREAM_STUDIO_HOME": str(home),
        "DS_HOME": str(home),
        "DS_SPOOL_ROOT": str(home / "events"),
        "DREAM_STUDIO_DB_PATH": str(home / "state" / "studio.db"),
    }, "an inherited variable beat --home"
    assert {k: os.environ.get(k) for k in inherited} == inherited, "not restored"


def test_render_follows_home_past_an_inherited_alternate_name(tmp_path, monkeypatch):
    """The round-2 finding, at the reader: `ds render` resolves its home from
    DS_DREAM_STUDIO_HOME first, and never receives --home as an argument."""
    from interfaces.cli import ds, ds_render

    monkeypatch.setenv("DS_DREAM_STUDIO_HOME", str(tmp_path / "decoy"))
    seen = {}
    monkeypatch.setattr(ds, "_run", lambda *a: seen.setdefault("home", ds_render._ds_home()) and 0)
    home = (tmp_path / "home").resolve()
    ds.main(["--home", str(home), "version"])
    assert seen["home"] == home


#: Environment names ending in HOME that are the operating system's, not Dream Studio's.
_OS_HOMES = {"HOME", "USERPROFILE"}


def test_every_home_name_production_code_reads_is_one_home_sets():
    """THE NEXT ALIAS FAILS HERE, not in a review. Twice the export missed a name the code
    reads -- first by precedence, then by a spelling (DS_DREAM_STUDIO_HOME) -- so the set
    is checked against what the code actually reads, not against what was remembered."""
    import re
    import subprocess

    from interfaces.cli.ds import home_variables

    files = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split()
    reads = re.compile(
        r"""(?:environ\.get|getenv|environ\[|setdefault)\(?\s*["']([A-Z0-9_]*HOME)["']"""
    )
    names = set()
    for rel in files:
        if rel.startswith(("tests/", "dist/")):
            continue
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        names.update(reads.findall(text))
    assert names, "the scan found no reads at all -- the pattern is broken, not the code clean"
    missing = names - _OS_HOMES - set(home_variables(Path("/h")))
    assert not missing, f"--home does not set {sorted(missing)}, which production code reads"


def test_diagnostics_follow_home_not_the_user_directory(tmp_path, monkeypatch):
    """Round 3: `ds --home X project register` wrote diagnostics under the real home,
    because the diagnostics directory spelled `Path.home() / ".dream-studio"` itself and
    never read DREAM_STUDIO_HOME -- the variable --home sets."""
    from core.telemetry.diagnostics import log_diagnostic

    fake_user = tmp_path / "user"
    fake_user.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_user))
    monkeypatch.setenv("USERPROFILE", str(fake_user))
    monkeypatch.delenv("DS_DIAGNOSTICS_DIR", raising=False)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))

    log_diagnostic("anomaly", "register_project", context={"probe": True})

    assert list((home / "state" / "diagnostics").glob("*.jsonl")), "not under --home"
    assert [p for p in fake_user.rglob("*") if p.is_file()] == []


#: The only places core/ and interfaces/ may spell the default home themselves, each for a
#: reason that is about the operator's REAL install rather than whichever home is in force.
_MAY_SPELL_THE_DEFAULT_HOME = {
    # The resolver.
    "core/config/paths.py",
    # Recognising and backing up the live authority: protection for the operator's real
    # database, which must not be redirected by the variable it protects against.
    "core/config/sqlite_bootstrap.py:_is_live_authority_db",
    "core/config/sqlite_bootstrap.py:_backup_live_db",
    # Cutover planning describes the live install on this machine.
    "core/upgrade/",
}


def test_core_and_the_cli_spell_the_default_home_in_one_place():
    """THE NEXT HARDCODED HOME FAILS HERE. Three review rounds each found one more way a
    `--home` command escaped its home; the third was a module that built the path itself.
    Every default home in core/ and interfaces/ goes through core.config.paths.home_dir()."""
    import ast
    import re
    import subprocess

    spelled = re.compile(
        r"""home\(\)\s*/\s*["']\.dream-studio|expanduser\(["']~/?\.dream-studio"""
        r"""|expanduser\(["']~["']\)\)?\s*/\s*["']\.dream-studio"""
    )
    files = subprocess.run(
        ["git", "ls-files", "core/*.py", "interfaces/*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split()
    assert len(files) > 100, "the scan found almost nothing -- the listing is broken"
    offenders = []
    for rel in files:
        if rel in _MAY_SPELL_THE_DEFAULT_HOME or any(
            rel.startswith(p) for p in _MAY_SPELL_THE_DEFAULT_HOME if p.endswith("/")
        ):
            continue
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if not spelled.search(text):
            continue
        functions = [
            n
            for n in ast.walk(ast.parse(text))
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        for lineno, line in enumerate(text.splitlines(), 1):
            if not spelled.search(line) or line.lstrip().startswith("#"):
                continue
            owner = next(
                (f.name for f in functions if f.lineno <= lineno <= (f.end_lineno or f.lineno)),
                None,
            )
            if f"{rel}:{owner}" not in _MAY_SPELL_THE_DEFAULT_HOME:
                offenders.append(f"{rel}:{lineno}")
    assert not offenders, f"spell the home through core.config.paths.home_dir(): {offenders}"
