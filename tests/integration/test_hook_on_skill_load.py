"""Integration test for on-skill-load."""

from __future__ import annotations

import io
import json

from lib import state


def test_logs_skill_read_to_usage_file(isolated_home, monkeypatch, capsys, handler):
    mod = handler("on-skill-load")
    skill_file = isolated_home / "skills" / "foo" / "bar.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("hello world", encoding="utf-8")

    payload = {"tool_name": "Read", "tool_input": {"file_path": str(skill_file)}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    log = isolated_home / ".dream-studio" / "meta" / "skill-usage.log"
    assert log.exists()
    contents = log.read_text(encoding="utf-8")
    assert "foo/bar" in contents


def test_non_read_tool_is_ignored(isolated_home, monkeypatch, handler):
    mod = handler("on-skill-load")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "skills/foo.md"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    log = isolated_home / ".dream-studio" / "meta" / "skill-usage.log"
    assert not log.exists()


def test_director_placeholder_emits_resolved_name(isolated_home, monkeypatch, capsys, handler):
    mod = handler("on-skill-load")
    skill_file = isolated_home / "skills" / "agent" / "coach.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("hello {{director_name}}!", encoding="utf-8")
    state.write_config({"director_name": "Alice"})

    payload = {"tool_name": "Read", "tool_input": {"file_path": str(skill_file)}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()
    out = capsys.readouterr().out
    assert "'Alice'" in out
