"""Integration test for on-context-threshold."""

from __future__ import annotations

import io
import json


def _write_jsonl(projects_dir, session_id: str, kb: float) -> None:
    projects_dir.mkdir(parents=True, exist_ok=True)
    p = projects_dir / f"{session_id}.jsonl"
    p.write_bytes(b"x" * int(kb * 1024))


def test_no_jsonl_is_noop(isolated_home, monkeypatch, handler):
    projects = isolated_home / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "abc"})))

    mod = handler("on-context-threshold")
    mod.main()  # no crash, no output needed


def test_urgent_reminds_not_blocks(isolated_home, monkeypatch, capsys, handler):
    """Urgent context emits a /compact reminder but never hard-blocks the prompt."""
    projects = isolated_home / "projects"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    _write_jsonl(projects, "s1", kb=5000)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s1"})))

    mod = handler("on-context-threshold")
    mod.main()

    out = capsys.readouterr().out
    assert "urgent" in out  # reminder fired
    assert "continue" not in out  # NOT a {"continue": false} block
    # once-per-session sentinel, no block sentinel
    assert (projects / ".urgent-msg-sentinel-s1").exists()
    assert not (projects / ".compact-sentinel-s1").exists()


def test_kb_baseline_suppresses_after_compact(isolated_home, monkeypatch, capsys, handler):
    """A post-compact KB baseline makes the size fallback measure growth since /compact,
    so a large append-only JSONL no longer reads as urgent."""
    projects = isolated_home / "projects"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    _write_jsonl(projects, "s2", kb=5000)
    # on-post-compact recorded the full size as the baseline → net growth ~0
    baseline = projects / ".kb-baseline-sentinel-s2"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text("5000")

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s2"})))
    mod = handler("on-context-threshold")
    mod.main()

    # band is "ok" → no reminder, no block
    out = capsys.readouterr().out
    assert "urgent" not in out
    assert "continue" not in out


def test_warn_band_prints_growing(isolated_home, monkeypatch, capsys, handler):
    projects = isolated_home / "projects"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    _write_jsonl(projects, "s3", kb=1800)
    # freshen mtime so it's recent
    (projects / "s3.jsonl").touch()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s3"})))

    mod = handler("on-context-threshold")
    mod.main()

    assert "growing" in capsys.readouterr().out


def test_warn_fires_once_per_5pp(isolated_home, monkeypatch, capsys, handler):
    """WARN band only prints when crossing a 5pp boundary, not on every prompt."""
    projects = isolated_home / "projects"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    _write_jsonl(projects, "sw", kb=1800)
    (projects / "sw.jsonl").touch()

    import json as _json
    import tempfile
    import time
    from pathlib import Path

    session_id = "sw"
    bridge_file = Path(tempfile.gettempdir()) / f"claude-ctx-{session_id}.json"
    bridge_file.write_text(
        _json.dumps(
            {
                "used_pct": 57.0,
                "raw_pct": 47.0,
                "timestamp": time.time(),
            }
        ),
        encoding="utf-8",
    )

    mod = handler("on-context-threshold")
    monkeypatch.setattr("sys.stdin", io.StringIO(_json.dumps({"session_id": session_id})))
    mod.main()
    out1 = capsys.readouterr().out
    assert "growing" in out1  # first crossing at 55pp floor → fires

    # Same percentage again — sentinel exists, should NOT fire
    monkeypatch.setattr("sys.stdin", io.StringIO(_json.dumps({"session_id": session_id})))
    mod.main()
    out2 = capsys.readouterr().out
    assert "growing" not in out2  # same floor, no re-fire

    bridge_file.unlink(missing_ok=True)


def test_projects_dir_slug_replaces_spaces(monkeypatch, handler):
    """Claude Code slug format replaces `:`, `\\`, `/`, AND spaces with `-`."""
    from pathlib import Path
    import sys

    # Add hooks lib to path and import the module where function moved
    plugin_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from control.context import monitor as context_monitor

    monkeypatch.delenv("CLAUDE_PROJECTS_DIR", raising=False)

    # Windows path with spaces — the common case
    win = Path("C:\\Users\\Example User\\studio")
    assert context_monitor.projects_dir_for_cwd(win).name == "C--Users-Example-User-studio"

    # Unix path with spaces
    unix = Path("/home/some user/work")
    assert context_monitor.projects_dir_for_cwd(unix).name == "-home-some-user-work"

    # No spaces — unchanged behavior
    plain = Path("C:\\code\\repo")
    assert context_monitor.projects_dir_for_cwd(plain).name == "C--code-repo"
