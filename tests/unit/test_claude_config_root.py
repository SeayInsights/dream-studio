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
import subprocess
from pathlib import Path

from core.config.paths import claude_config_root

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
