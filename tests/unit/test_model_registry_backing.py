"""WO-GRADER-PROFILE-REGISTRY task 1: the model_registry declaration is honest — every
table it names as a source must exist in the lean baseline. It was neutralized (no
backing table) rather than resurrecting the deliberately-dropped model_provider_profiles.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.shared_intelligence.model_registry import MODEL_REGISTRY_SOURCE_TABLES


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
