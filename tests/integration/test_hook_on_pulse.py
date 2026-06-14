"""Integration test for on-pulse."""

from __future__ import annotations

import json

from freezegun import freeze_time

FROZEN = "2026-01-01 12:00:00"


@freeze_time(FROZEN)
def test_generates_healthy_report_without_github(isolated_home, monkeypatch, handler):
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    mod = handler("on-pulse")
    mod.main()

    meta = isolated_home / ".dream-studio" / "meta"
    report = meta / "pulse-2026-01-01.md"
    latest = meta / "pulse-latest.json"

    assert report.exists()
    assert "HEALTHY" in report.read_text(encoding="utf-8")
    doc = json.loads(latest.read_text(encoding="utf-8"))
    assert doc["health"] == "HEALTHY"
    assert doc["schema_version"] == 1


@freeze_time(FROZEN)
def test_respects_github_repo_from_config(isolated_home, monkeypatch, handler):
    from core.config import state

    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    state.write_config({"github_repo": "acme/widgets"})

    mod = handler("on-pulse")
    mod.main()

    report = (isolated_home / ".dream-studio" / "meta" / "pulse-2026-01-01.md").read_text(
        encoding="utf-8"
    )
    assert "acme/widgets" in report


def test_pending_drafts_are_counted(isolated_home, handler):
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from core.event_store.studio_db import insert_lesson
    from core.config import paths

    db_path = paths.state_dir() / "studio.db"
    insert_lesson("test-lesson-1", "test-source", "Lesson One", db_path=db_path)
    insert_lesson("test-lesson-2", "test-source", "Lesson Two", db_path=db_path)

    mod = handler("on-pulse")
    mod.main()

    latest = isolated_home / ".dream-studio" / "meta" / "pulse-latest.json"
    doc = json.loads(latest.read_text(encoding="utf-8"))
    assert doc["pending_drafts"] == 2
