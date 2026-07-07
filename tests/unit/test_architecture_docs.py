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


# WO-DOC-DATABASE: DATABASE.md + MIGRATION_AUTHORITY.md must reflect the three-store
# reality + the lean baseline, be clean text, and cross-link the canonical arch doc.
DATABASE_DOC = REPO_ROOT / "docs" / "DATABASE.md"
MIGRATION_DOC = REPO_ROOT / "docs" / "MIGRATION_AUTHORITY.md"


def test_db_docs_exist_and_are_clean_text():
    for doc in (DATABASE_DOC, MIGRATION_DOC):
        raw = doc.read_bytes()
        assert raw, f"{doc.name} missing/empty"
        assert b"\x00" not in raw, f"{doc.name} contains a NUL byte (encoding corruption)"


def test_db_docs_reflect_baseline_and_three_store():
    db = DATABASE_DOC.read_text(encoding="utf-8")
    mig = MIGRATION_DOC.read_text(encoding="utf-8")
    assert "three-store-data-architecture.md" in db, "DATABASE.md must cross-link the arch doc"
    assert (
        "three-store-data-architecture.md" in mig
    ), "MIGRATION_AUTHORITY.md must cross-link the arch doc"
    assert (
        "142_lean_baseline" in mig and "143" in mig
    ), "MIGRATION doc must state the lean baseline + forward head"
    for store in ("studio.db", "aggregate_metrics.db", "files.db"):
        assert store in db, f"DATABASE.md must describe {store}"
