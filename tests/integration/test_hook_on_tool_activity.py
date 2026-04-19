"""Integration test for on-tool-activity."""

from __future__ import annotations

import io
import json


def test_writes_activity_entry(isolated_home, monkeypatch, handler):
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "C:/foo/bar.py"},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod = handler("on-tool-activity")
    mod.main()

    target = isolated_home / ".dream-studio" / "state" / "activity.json"
    assert target.exists()
    doc = json.loads(target.read_text(encoding="utf-8"))
    agents = doc["agents"]
    assert len(agents) == 1
    assert agents[0]["name"] == "Code Editor"
    assert agents[0]["task"] == "Edit: bar.py"
    assert agents[0]["status"] == "running"


def test_caps_entries_at_max(isolated_home, monkeypatch, handler):
    target = isolated_home / ".dream-studio" / "state" / "activity.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    # seed with 6 existing entries
    import time
    now = time.time()
    target.write_text(
        json.dumps(
            {
                "agents": [
                    {"id": i, "name": "dream-studio Agent", "status": "running",
                     "task": f"t{i}", "elapsed": "just now", "ts": now - i}
                    for i in range(6)
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod = handler("on-tool-activity")
    mod.main()

    doc = json.loads(target.read_text(encoding="utf-8"))
    assert len(doc["agents"]) == 6  # MAX_AGENTS
    assert doc["agents"][0]["task"] == "$ ls"


def test_harden_nudge_uses_project_root(isolated_home, tmp_path, monkeypatch, capsys, handler):
    # File deep in a subdir — project root (tmp_path) has no Makefile/SECURITY.md
    subdir = tmp_path / "src" / "utils"
    subdir.mkdir(parents=True)
    file_path = str(subdir / "helper.py")

    payload = {"tool_name": "Edit", "tool_input": {"file_path": file_path}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod = handler("on-tool-activity")
    # Patch _project_root to return tmp_path (simulating no Makefile at root)
    monkeypatch.setattr(mod, "_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "harden" in out.lower()


def test_harden_nudge_suppressed_when_makefile_at_root(isolated_home, tmp_path, monkeypatch, capsys, handler):
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
    file_path = str(tmp_path / "src" / "app.py")

    payload = {"tool_name": "Edit", "tool_input": {"file_path": file_path}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod = handler("on-tool-activity")
    monkeypatch.setattr(mod, "_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "harden" not in out.lower()


def test_security_suggest_fires_for_auth_file(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Edit of auth/login.py triggers security suggest nudge."""
    auth = tmp_path / "auth"
    auth.mkdir()
    file_path = str(auth / "login.py")

    payload = {"tool_name": "Edit", "tool_input": {"file_path": file_path}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod = handler("on-tool-activity")
    # Patch _project_root to return tmp_path (no Makefile/SECURITY.md — harden nudge also fires)
    monkeypatch.setattr(mod, "_project_root", lambda _: tmp_path)
    mod.main()

    out = capsys.readouterr().out
    assert "Security" in out
    assert "login.py" in out
    assert "/secure" in out


def test_security_suggest_suppressed_after_first(isolated_home, tmp_path, monkeypatch, capsys, handler):
    """Security suggest fires once, then sentinel suppresses subsequent calls."""
    auth = tmp_path / "auth"
    auth.mkdir()
    file_path = str(auth / "login.py")

    mod = handler("on-tool-activity")
    monkeypatch.setattr(mod, "_project_root", lambda _: tmp_path)

    # First call — should fire
    payload = {"tool_name": "Edit", "tool_input": {"file_path": file_path}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()
    out1 = capsys.readouterr().out
    assert "Security" in out1

    # Second call — sentinel exists, should be suppressed
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()
    out2 = capsys.readouterr().out
    # Security suggest should NOT appear again
    assert "Security" not in out2
