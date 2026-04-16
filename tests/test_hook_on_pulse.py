"""Integration test for on-pulse."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def test_generates_healthy_report_without_github(isolated_home, monkeypatch, handler):
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    mod = handler("on-pulse")
    mod.main()

    meta = isolated_home / ".dream-studio" / "meta"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = meta / f"pulse-{date_str}.md"
    latest = meta / "pulse-latest.json"

    assert report.exists()
    assert "HEALTHY" in report.read_text(encoding="utf-8")
    doc = json.loads(latest.read_text(encoding="utf-8"))
    assert doc["health"] == "HEALTHY"
    assert doc["schema_version"] == 1


def test_respects_github_repo_from_config(isolated_home, monkeypatch, handler):
    from lib import state

    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    state.write_config({"github_repo": "acme/widgets"})

    mod = handler("on-pulse")
    mod.main()

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = (isolated_home / ".dream-studio" / "meta" / f"pulse-{date_str}.md").read_text(encoding="utf-8")
    assert "acme/widgets" in report


def test_pending_drafts_are_counted(isolated_home, handler):
    drafts = isolated_home / ".dream-studio" / "meta" / "draft-lessons"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "one.md").write_text("x", encoding="utf-8")
    (drafts / "two.md").write_text("x", encoding="utf-8")

    mod = handler("on-pulse")
    mod.main()

    latest = isolated_home / ".dream-studio" / "meta" / "pulse-latest.json"
    doc = json.loads(latest.read_text(encoding="utf-8"))
    assert doc["pending_drafts"] == 2
