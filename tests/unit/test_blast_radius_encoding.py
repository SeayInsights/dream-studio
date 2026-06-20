"""Regression: blast-radius git-diff capture must decode UTF-8 on all platforms.

WO-BLAST-UTF8 (found during WO-P20-AGENTS-GEN): `_git` ran the diff subprocess
with text=True and the platform default codec. On Windows (cp1252) a diff
containing UTF-8 bytes (em-dashes / routing glyphs in the generated AGENTS.md)
raised UnicodeDecodeError in the reader thread, returning a partial/None diff and
crashing the stale-symbol detector. Forcing encoding="utf-8" fixes it.
"""

from __future__ import annotations

import subprocess

from core.gates.blast_radius import _git


def _run(args, cwd):
    subprocess.run(args, cwd=cwd, capture_output=True, check=True)


def test_git_diff_decodes_utf8(tmp_path):
    """A diff containing non-cp1252 UTF-8 bytes round-trips through _git intact."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@example.com"], repo)
    _run(["git", "config", "user.name", "t"], repo)

    f = repo / "AGENTS.md"
    f.write_text("base line\n", encoding="utf-8")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-qm", "base"], repo)

    # Add content with the exact glyphs the generator emits (em-dash, middot,
    # ellipsis, ≥, ✓) — these are the bytes that broke cp1252 decoding.
    f.write_text("base line\nrouting — a · b … c ≥ d ✓ done\n", encoding="utf-8")

    diff = _git(["diff", "HEAD"], repo)
    assert "routing" in diff, "diff must be captured without a decode crash"
    assert "—" in diff and "≥" in diff, "UTF-8 glyphs must survive the capture"
