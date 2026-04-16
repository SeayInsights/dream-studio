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
