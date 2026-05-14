from __future__ import annotations

from pathlib import Path

DOC = Path("docs/demo-disaster-prevention-scenario.md")


def test_demo_scenario_names_the_risky_bundled_action_and_guardrails() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "clean up old Dream Studio state and ship the release" in text
    assert "deletion, archive execution, compaction, DB cleanup, push, tag, deploy" in text
    assert "approval boundaries" in text


def test_demo_scenario_uses_telemetry_dashboard_and_validation() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Telemetry records the route decision" in text
    assert "Dashboard attention" in text
    assert "Validation result" in text
    assert "Decision record" in text


def test_demo_scenario_preserves_safe_demo_boundaries() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Use temp or rehearsal state" in text
    assert "Do not mutate external projects" in text
    assert "Do not push or deploy" in text
    assert "derived telemetry, not primary authority" in text
