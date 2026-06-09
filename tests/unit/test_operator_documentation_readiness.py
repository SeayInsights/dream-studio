from __future__ import annotations

from pathlib import Path

DOC = Path("docs/operator-guide.md")


def test_operator_guide_documents_local_first_boundaries() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "local-first AI orchestration" in text
    assert "Repo source, local runtime state, SQLite authority" in text
    assert "canonical path resolution" in text
    assert "should not hardcode operator-specific paths" in text


def test_operator_guide_documents_dashboard_and_cutover_boundaries() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "derived_view: true" in text
    assert "primary_authority: false" in text
    assert "separate cleanup approval boundary" in text
    assert "Cleanup, archive, deletion, compaction, deduplication" in text


def test_operator_guide_documents_demo_and_safety_checklist() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "## Demo Readiness" in text
    assert "temp or rehearsal DB" in text
    assert "Approved files are listed before mutation" in text
    assert "Push, tag, deploy, cleanup" in text
