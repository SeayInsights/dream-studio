"""WO-DOC-ARCH: the canonical three-store architecture doc must exist and describe
the three stores, the event spine, and the store-placement rubric — so the doc stays
a real contract, not an empty stub.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCH_DOC = REPO_ROOT / "docs" / "architecture" / "three-store-data-architecture.md"


def test_three_store_doc_exists():
    assert ARCH_DOC.is_file(), "three-store architecture doc missing"


def test_three_store_doc_names_the_three_stores():
    text = ARCH_DOC.read_text(encoding="utf-8")
    for store in ("studio.db", "aggregate_metrics.db", "files.db"):
        assert store in text, f"architecture doc must describe {store}"


def test_three_store_doc_covers_spine_and_rubric():
    text = ARCH_DOC.read_text(encoding="utf-8").lower()
    assert "correlation_id" in text, "doc must describe the business/ai canonical join"
    assert "ingestor" in text, "doc must describe the event spine ingestor"
    assert "rubric" in text, "doc must include the store-placement rubric"
    assert "derived" in text, "doc must state DuckDB is derived/rebuildable"
