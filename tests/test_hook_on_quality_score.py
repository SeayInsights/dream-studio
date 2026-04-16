"""Integration test for on-quality-score."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def test_no_marker_is_noop(isolated_home, handler):
    mod = handler("on-quality-score")
    mod.main()
    assert not (isolated_home / ".dream-studio" / "meta" / "quality-score.json").exists()


def test_runs_checks_with_marker(isolated_home, monkeypatch, handler):
    # Place marker, stub git helpers to return synthetic diff/file list
    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps({"command": "build feature: y", "started_at": started}))

    mod = handler("on-quality-score")
    monkeypatch.setattr(mod, "changed_files", lambda cwd, since: ["src/app.py"])
    monkeypatch.setattr(mod, "diff_content", lambda cwd, since: "+print('debug thing')\n")

    # make src/app.py exist so large-file check can read it
    (isolated_home / "src").mkdir(parents=True, exist_ok=True)
    (isolated_home / "src" / "app.py").write_text("x\n" * 10, encoding="utf-8")
    monkeypatch.chdir(isolated_home)

    mod.main()

    score_file = isolated_home / ".dream-studio" / "meta" / "quality-score.json"
    assert score_file.exists()
    doc = json.loads(score_file.read_text(encoding="utf-8"))
    assert doc["command"] == "build feature: y"
    # debug pattern should have flagged
    assert doc["results"]["debug"]["status"] == "FLAG"


def test_secret_pattern_fails(isolated_home, monkeypatch, handler):
    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps({"command": "deploy: prod", "started_at": started}))

    mod = handler("on-quality-score")
    monkeypatch.setattr(mod, "changed_files", lambda cwd, since: ["src/secrets.py"])
    monkeypatch.setattr(
        mod, "diff_content",
        lambda cwd, since: "+api_key = 'abcdef1234567890abcd'\n",
    )
    monkeypatch.chdir(isolated_home)

    mod.main()

    doc = json.loads((isolated_home / ".dream-studio" / "meta" / "quality-score.json").read_text(encoding="utf-8"))
    assert doc["results"]["secrets"]["status"] == "FAIL"
