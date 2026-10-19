"""An explicit CLAUDE_CONFIG_DIR is the root Dream Studio writes to.

claude_config_root() returned the authority's active business profile's
claude_config_dir BEFORE CLAUDE_CONFIG_DIR. A shell that named one Claude Code root
in its environment had `ds doctor --fix` and `ds integrate install` (without
--config-root) write into the profile's root instead -- for an authority copied from
another machine or home, the operator's real Claude Code settings. And doctor --fix
spawned integrate with no --config-root, so integrate guessed from the working
directory and wrote a git pre-push hook into whatever repository that was.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _seed_profile(db: Path, claude_config_dir: Path) -> None:
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_profiles"
            " (profile_id, client_id, name, claude_config_dir, status, created_at, updated_at)"
            " VALUES ('p1', 'c1', 'P', ?, 'active',"
            " '2026-10-02T00:00:00+00:00', '2026-10-02T00:00:00+00:00')",
            (str(claude_config_dir),),
        )
        conn.commit()
    finally:
        conn.close()


def _env(tmp: Path, home: Path, env_root: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("DREAM_STUDIO", "DS_", "CLAUDE_", "PYTHON"))
    }
    user = tmp / "user"
    user.mkdir(exist_ok=True)
    env.update(
        {
            "HOME": str(user),
            "USERPROFILE": str(user),
            "DREAM_STUDIO_HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(env_root),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _home_with_profile(tmp: Path, profile_root: Path, monkeypatch) -> Path:
    from core.config.sqlite_bootstrap import bootstrap_database

    home = tmp / "home"
    (home / "state").mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")  # business_profiles is 159
    bootstrap_database(home / "state" / "studio.db")
    _seed_profile(home / "state" / "studio.db", profile_root)
    return home


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


def test_an_explicit_claude_config_dir_wins_over_the_active_profile(tmp_path, monkeypatch):
    from core.config.paths import claude_config_root, claude_config_root_with_reason

    profile_root, env_root = tmp_path / "P", tmp_path / "E"
    home = _home_with_profile(tmp_path, profile_root, monkeypatch)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(env_root))
    assert claude_config_root() == env_root
    root, reason = claude_config_root_with_reason()
    assert root == env_root and "CLAUDE_CONFIG_DIR" in reason

    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    root, reason = claude_config_root_with_reason()
    assert root == profile_root and "profile" in reason


def test_doctor_fix_from_an_unrelated_repo_writes_only_the_root_it_examined(tmp_path, monkeypatch):
    """The whole path, run for real: a fresh authority whose active profile names root
    P, the environment naming root E, the working directory an unrelated git
    repository. Every write lands in E; P and the repository are untouched."""
    profile_root, env_root = tmp_path / "P", tmp_path / "E"
    home = _home_with_profile(tmp_path, profile_root, monkeypatch)
    repo = tmp_path / "unrelated-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    hooks_before = _files(repo / ".git" / "hooks")

    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", "--home", str(home), "doctor", "--fix"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo,
        env={**_env(tmp_path, home, env_root), "PYTHONPATH": str(REPO)},
        timeout=900,
    )
    assert "install: ran integrate install" in proc.stdout + proc.stderr, (
        proc.stdout[-2000:] + proc.stderr[-2000:]
    )
    assert (
        _files(profile_root) == []
    ), f"doctor --fix wrote into the profile's root: {_files(profile_root)}"
    assert (env_root / "settings.json").is_file(), "nothing was installed into CLAUDE_CONFIG_DIR"
    assert (
        _files(repo / ".git" / "hooks") == hooks_before
    ), "a git hook was written into the cwd's repo"
    assert not (repo / ".claude").exists()


def test_integrate_without_a_root_says_which_root_it_chose_and_why(tmp_path, monkeypatch):
    profile_root, env_root = tmp_path / "P", tmp_path / "E"
    home = _home_with_profile(tmp_path, profile_root, monkeypatch)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "interfaces.cli.ds",
            "--home",
            str(home),
            "integrate",
            "install",
            "claude_code",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env={**_env(tmp_path, home, env_root), "PYTHONPATH": str(REPO)},
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert f"{env_root}" in proc.stderr and "CLAUDE_CONFIG_DIR" in proc.stderr, proc.stderr[-2000:]
    start = proc.stdout.index("{")
    report = json.loads(proc.stdout[start:])
    assert report["config_root"] == str(env_root)
    assert "CLAUDE_CONFIG_DIR" in report["config_root_reason"]
