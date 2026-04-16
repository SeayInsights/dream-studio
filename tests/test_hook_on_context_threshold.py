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


def test_urgent_blocks_prompt(isolated_home, monkeypatch, capsys, handler):
    projects = isolated_home / "projects"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    _write_jsonl(projects, "s1", kb=5000)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s1"})))

    mod = handler("on-context-threshold")
    mod.main()

    out = capsys.readouterr().out.strip()
    result = json.loads(out)
    assert result["continue"] is False
    assert "auto-blocked" in result["stopReason"]
    # sentinel should exist so the next prompt passes through
    assert (projects / ".compact-sentinel-s1").exists()


def test_sentinel_clears_and_passes(isolated_home, monkeypatch, handler):
    projects = isolated_home / "projects"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    _write_jsonl(projects, "s2", kb=5000)
    sentinel = projects / ".compact-sentinel-s2"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("5000")

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s2"})))
    mod = handler("on-context-threshold")
    mod.main()

    # sentinel is consumed, no stopReason printed
    assert not sentinel.exists()


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
