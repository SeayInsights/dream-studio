"""Integration test for on-milestone-end."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def test_no_marker_is_noop(isolated_home, handler):
    mod = handler("on-milestone-end")
    mod.main()

    log = isolated_home / ".dream-studio" / "meta" / "milestone-log.md"
    assert not log.exists()


def test_marker_cleared_and_logged(isolated_home, handler):
    mod = handler("on-milestone-end")
    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps({"command": "build feature: x", "started_at": started}))

    mod.main()

    assert not marker.exists()
    log = isolated_home / ".dream-studio" / "meta" / "milestone-log.md"
    assert log.exists()
    assert "build feature: x" in log.read_text(encoding="utf-8")


def test_long_milestone_drafts_lesson(isolated_home, handler):
    mod = handler("on-milestone-end")
    marker = isolated_home / ".dream-studio" / "state" / "milestone-active.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    started = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    marker.write_text(json.dumps({"command": "build feature: huge", "started_at": started}))

    mod.main()

    drafts = list((isolated_home / ".dream-studio" / "meta" / "draft-lessons").glob("long-milestone-*.md"))
    assert len(drafts) == 1
    assert "Long-Running Milestone" in drafts[0].read_text(encoding="utf-8")
