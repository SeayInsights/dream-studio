"""Integration test for on-milestone-start."""

from __future__ import annotations

import json


def test_writes_marker_on_dcl_command(isolated_home, monkeypatch, handler):
    mod = handler("on-milestone-start")
    monkeypatch.setenv("CLAUDE_USER_MESSAGE_TEXT", "build feature: widgets")
    mod.main()

    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    assert marker.exists()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["command"] == "build feature: widgets"
    assert "started_at" in data


def test_non_matching_prompt_no_marker(isolated_home, monkeypatch, handler):
    mod = handler("on-milestone-start")
    monkeypatch.setenv("CLAUDE_USER_MESSAGE_TEXT", "just chatting")
    mod.main()

    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    assert not marker.exists()


def test_duplicate_marker_is_preserved(isolated_home, monkeypatch, handler, capsys):
    mod = handler("on-milestone-start")
    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"command": "original", "started_at": "x"}))

    monkeypatch.setenv("CLAUDE_USER_MESSAGE_TEXT", "deploy: prod")
    mod.main()

    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["command"] == "original"
    assert "already active" in capsys.readouterr().out
