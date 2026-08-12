"""WO-GRADER-PROFILE-REGISTRY task 1: the model_registry declaration is honest — every
table it names as a source must exist in the lean baseline. It was neutralized (no
backing table) rather than resurrecting the deliberately-dropped model_provider_profiles.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.shared_intelligence.model_registry import (
    MODEL_REGISTRY_SOURCE_TABLES,
    model_provider_capability_matrix,
    model_provider_registry_summary,
)


def _baseline_tables() -> set[str]:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "boot.db"
        bootstrap_database(db)
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        finally:
            conn.close()
    return {r[0] for r in rows}


def test_declared_source_tables_exist_in_baseline():
    baseline = _baseline_tables()
    missing = [t for t in MODEL_REGISTRY_SOURCE_TABLES if t not in baseline]
    assert not missing, (
        f"model_registry declares source tables absent from the baseline: {missing}. "
        "The declaration must be honest — either the table exists or it is not declared."
    )


def test_no_query_against_the_dropped_table():
    """gap c6fc31b1: the dead SELECT against the dropped model_provider_profiles is gone —
    the source, not just the runtime behavior, must be free of it."""
    src = Path(__file__).resolve().parents[2] / "core" / "shared_intelligence" / "model_registry.py"
    text = src.read_text(encoding="utf-8")
    assert "FROM model_provider_profiles" not in text, "no SELECT against the dropped table"
    assert ".execute(" not in text, "the read model executes no SQL against a backing table"


def _bootstrapped_conn():
    d = tempfile.mkdtemp()
    db = Path(d) / "boot.db"
    bootstrap_database(db)
    return sqlite3.connect(str(db))


def test_registry_summary_returns_documented_empty_state():
    """gap c6fc31b1 task 2: against a freshly bootstrapped baseline (no backing table) the
    summary read model returns the documented honest empty-state shape end-to-end."""
    conn = _bootstrapped_conn()
    try:
        summary = model_provider_registry_summary(conn)
    finally:
        conn.close()
    assert summary["model_count"] == 0
    assert summary["profiles"] == []
    assert summary["provider_counts"] == {}
    assert summary["facts_available"] is False
    assert summary["provider_api_calls_performed"] is False
    assert summary["empty_state"]  # a non-empty explanation string


def test_capability_matrix_returns_documented_empty_state():
    conn = _bootstrapped_conn()
    try:
        matrix = model_provider_capability_matrix(conn, required_capabilities=("reasoning",))
    finally:
        conn.close()
    assert matrix["matches"] == []
    assert matrix["match_count"] == 0
    assert matrix["matches_by_provider"] == {}
    assert matrix["facts_available"] is False
    assert matrix["empty_state"]
