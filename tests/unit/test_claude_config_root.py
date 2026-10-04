"""claude_config_root() means Claude Code's config root -- CLAUDE_CONFIG_DIR, else ~/.claude.

WHY THIS FILE EXISTS. Dream Studio never read CLAUDE_CONFIG_DIR anywhere: twelve call
sites spelled `Path.home() / ".claude"` directly, including
core.event_store.project_attribution._transcript_root() -- the function that reads
Claude Code session transcripts for AI-spend attribution. An operator running a second,
separate Claude Code identity for a different engagement (its own CLAUDE_CONFIG_DIR,
pointed away from ~/.claude) could install Dream Studio's hooks there and Dream Studio
would still never see a single one of that identity's transcripts, because every reader
went straight to the default instead of asking.

Mirrors tests/unit/test_home_means_home.py's pattern for home_dir() / DREAM_STUDIO_HOME,
but for a conceptually distinct thing: that file guards Dream Studio's OWN home; this one
guards the config root of the Claude Code CLI itself, which the real `claude` binary
relocates with CLAUDE_CONFIG_DIR. Do not conflate the two in either direction.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
from pathlib import Path

from core.config.paths import claude_config_root
from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_claude_config_root_honors_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-fulcrum"))
    assert claude_config_root() == tmp_path / "claude-fulcrum"


def test_claude_config_root_expands_a_tilde_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "~/claude-fulcrum")
    assert claude_config_root() == tmp_path / "claude-fulcrum"


def test_claude_config_root_falls_back_to_the_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert claude_config_root() == tmp_path / ".claude"


# ── active-profile precedence (migration 159, core/profiles/) ─────────────────────


def _seed_active_profile(db_path: Path, *, claude_config_dir: str | None) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_profiles"
            " (profile_id, client_id, name, claude_config_dir, status, created_at, updated_at)"
            " VALUES ('p1', 'seayinsights', 'P', ?, 'active',"
            " '2026-10-02T00:00:00+00:00', '2026-10-02T00:00:00+00:00')",
            (claude_config_dir,),
        )
        conn.commit()
    finally:
        conn.close()


def test_claude_config_root_prefers_the_active_profiles_config_dir(monkeypatch, tmp_path):
    """The active profile's claude_config_dir wins even when CLAUDE_CONFIG_DIR is also set."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    profile_dir = tmp_path / "claude-fulcrum-profile"
    _seed_active_profile(db_path, claude_config_dir=str(profile_dir))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-env-var"))

    assert claude_config_root() == profile_dir


def test_claude_config_root_falls_back_to_env_var_when_profile_has_no_config_dir(
    monkeypatch, tmp_path
):
    """An active profile with claude_config_dir unset (None) falls through to the env var."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    _seed_active_profile(db_path, claude_config_dir=None)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    env_dir = tmp_path / "claude-env-var"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(env_dir))

    assert claude_config_root() == env_dir


def test_claude_config_root_falls_back_to_default_when_profile_config_dir_is_empty(
    monkeypatch, tmp_path
):
    """An active profile with claude_config_dir == '' is treated as unset, not a real path."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    _seed_active_profile(db_path, claude_config_dir="")
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert claude_config_root() == tmp_path / ".claude"


def test_claude_config_root_falls_back_when_no_profile_is_active(monkeypatch, tmp_path):
    """business_profiles exists (migration 159 applied) but has zero active rows."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    env_dir = tmp_path / "claude-env-var"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(env_dir))

    assert claude_config_root() == env_dir


def test_claude_config_root_falls_back_when_profiles_table_is_missing(monkeypatch, tmp_path):
    """A pre-migration-159 DB (file exists, business_profiles does not) never raises."""
    db_path = tmp_path / "studio.db"
    sqlite3.connect(str(db_path)).close()
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    env_dir = tmp_path / "claude-env-var"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(env_dir))

    assert claude_config_root() == env_dir


def test_claude_config_root_falls_back_when_no_db_exists_at_all(monkeypatch, tmp_path):
    """A fresh checkout with no Dream Studio authority DB at all never raises."""
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(tmp_path / "nonexistent-dir" / "studio.db"))
    env_dir = tmp_path / "claude-env-var"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(env_dir))

    assert claude_config_root() == env_dir


def test_claude_config_root_logs_but_does_not_raise_on_a_broken_profiles_table(
    monkeypatch, tmp_path
):
    """A caught lookup failure is reported via log_diagnostic, not silently swallowed."""
    db_path = tmp_path / "studio.db"
    sqlite3.connect(str(db_path)).close()
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    calls = []
    monkeypatch.setattr(
        "core.telemetry.diagnostics.log_diagnostic",
        lambda **kwargs: calls.append(kwargs),
    )

    assert claude_config_root() == tmp_path / ".claude"
    assert len(calls) == 1
    assert calls[0]["source"] == "core.config.paths.claude_config_root"
    assert calls[0]["details"]["error_type"] == "OperationalError"


#: Trees the rule reaches, matching the bug report's own scope exactly.
_SCANNED_TREES = ("core/*.py", "interfaces/*.py", "integrations/*.py", "control/*.py")

#: The resolver itself is allowed to spell the literal it defines.
_EXEMPT_FILES = ("core/config/paths.py",)

#: `Path.home() / ".claude"` (either quote style) or the `.joinpath(".claude")` spelling,
#: with Path.home() on either side of a newline so a wrapped expression is still caught.
_HARDCODE = re.compile(
    r"""Path\.home\(\)\s*(?:/\s*|\.joinpath\(\s*)["']\.claude["']""",
)


def test_no_module_spells_claude_home_directly_instead_of_claude_config_root():
    """THE NEXT HARDCODED CLAUDE HOME FAILS HERE. Any file in core/, interfaces/,
    integrations/, or control/ that spells `Path.home() / ".claude"` (or the
    `.joinpath` equivalent) itself bypasses CLAUDE_CONFIG_DIR -- go through
    core.config.paths.claude_config_root() instead."""
    files = subprocess.run(
        ["git", "ls-files", *_SCANNED_TREES],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split()
    assert len(files) > 50, "the scan found almost nothing -- the listing is broken"

    offenders = []
    for rel in files:
        if rel.startswith(_EXEMPT_FILES):
            continue
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if _HARDCODE.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert offenders == [], (
        "spell Claude Code's config root through core.config.paths.claude_config_root():\n"
        + "\n".join(offenders)
    )


def test_project_scoped_dot_claude_is_not_flagged():
    """Sanity check on the guard itself: a project-relative `.claude` (detector.py's
    `cwd / ".claude"`, or this repo's own `REPO_ROOT / ".claude" / "hooks"`) is correct
    and must never trip the hardcode pattern -- only Path.home() combined with ".claude"
    is the bug."""
    assert not _HARDCODE.search('config_root = cwd / ".claude"')
    assert not _HARDCODE.search('REPO_ROOT / ".claude" / "hooks"')
    assert _HARDCODE.search('Path.home() / ".claude"')
    assert _HARDCODE.search("Path.home() / '.claude'")
