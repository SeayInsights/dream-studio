"""Integration test for on-quality-score."""

from __future__ import annotations

import json
import sys
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import patch

# Add hooks lib to path
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from control.analysis import quality_scoring  # noqa: E402


def test_no_marker_is_noop(isolated_home, handler):
    mod = handler("on-quality-score")
    mod.main()
    assert not (isolated_home / ".dream-studio" / "meta" / "quality-score.json").exists()


def test_runs_checks_with_marker(isolated_home, monkeypatch, handler):
    # Place marker, stub git helpers to return synthetic diff/file list
    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).isoformat()
    marker.write_text(json.dumps({"command": "build feature: y", "started_at": started}))

    mod = handler("on-quality-score")

    # make src/app.py exist so large-file check can read it
    (isolated_home / "src").mkdir(parents=True, exist_ok=True)
    (isolated_home / "src" / "app.py").write_text("x\n" * 10, encoding="utf-8")
    monkeypatch.chdir(isolated_home)

    with (
        patch.object(quality_scoring, "_changed_files", return_value=["src/app.py"]),
        patch.object(quality_scoring, "_diff_content", return_value="+print('debug thing')\n"),
    ):
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
    started = datetime.now(UTC).isoformat()
    marker.write_text(json.dumps({"command": "deploy: prod", "started_at": started}))

    mod = handler("on-quality-score")
    monkeypatch.chdir(isolated_home)

    with (
        patch.object(quality_scoring, "_changed_files", return_value=["src/secrets.py"]),
        patch.object(
            quality_scoring, "_diff_content", return_value="+api_key = 'abcdef1234567890abcd'\n"
        ),
    ):
        mod.main()

    doc = json.loads(
        (isolated_home / ".dream-studio" / "meta" / "quality-score.json").read_text(
            encoding="utf-8"
        )
    )
    assert doc["results"]["secrets"]["status"] == "FAIL"
