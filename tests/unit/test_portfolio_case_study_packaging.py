from __future__ import annotations

from pathlib import Path

DOC = Path("docs/portfolio-case-study.md")


def test_case_study_contains_architecture_and_positioning() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "local-first AI orchestration" in text
    assert "```mermaid" in text
    assert "Route model" in text
    assert "Dashboard" in text


def test_case_study_contains_evidence_metrics_and_screenshots() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "## Evidence-Backed Proof Points" in text
    assert "## Metrics To Capture" in text
    assert "## Screenshot Checklist" in text
    assert "Dashboard Telemetry Traceability section" in text


def test_case_study_keeps_caveats_and_no_fabricated_claims_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "## Known Caveats" in text
    assert "Cleanup execution remains deferred" in text
    assert "Docker profiles are optional" in text
    assert "not cloud product assumptions" in text
