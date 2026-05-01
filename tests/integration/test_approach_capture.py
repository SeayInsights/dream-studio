"""Integration tests for approach capture (raw_approaches table + capture_approach)."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.studio_db import (  # noqa: E402
    _connect,
    insert_approach,
    get_approach_patterns,
    get_best_approaches,
    capture_approach,
    rolling_window_prune,
)


def test_schema_includes_approaches_table(tmp_path):
    db = tmp_path / "test.db"
    conn = _connect(db)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()}
    conn.close()
    assert "raw_approaches" in tables
    assert "vw_approach_patterns" in tables


def test_insert_approach_round_trip(tmp_path):
    db = tmp_path / "test.db"
    ok = insert_approach("core:build", "parallel subagents", "success",
                         context="3 independent tasks", why="faster", db_path=db)
    assert ok is True
    conn = _connect(db)
    row = conn.execute("SELECT * FROM raw_approaches WHERE skill_id='core:build'").fetchone()
    conn.close()
    assert row is not None
    assert row["approach"] == "parallel subagents"
    assert row["outcome"] == "success"
    assert row["context"] == "3 independent tasks"
    assert row["why_worked"] == "faster"


def test_patterns_require_minimum_two(tmp_path):
    db = tmp_path / "test.db"
    insert_approach("core:build", "solo approach", "success", db_path=db)
    patterns = get_approach_patterns("core:build", db_path=db)
    assert len(patterns) == 0, "Should not surface patterns with only 1 entry"


def test_patterns_aggregation(tmp_path):
    db = tmp_path / "test.db"
    insert_approach("core:build", "parallel", "success", db_path=db)
    insert_approach("core:build", "parallel", "success", db_path=db)
    insert_approach("core:build", "parallel", "failure", db_path=db)
    insert_approach("core:build", "sequential", "failure", db_path=db)
    insert_approach("core:build", "sequential", "failure", db_path=db)

    patterns = get_approach_patterns("core:build", db_path=db)
    assert len(patterns) == 2

    by_approach = {p["approach"]: p for p in patterns}
    assert by_approach["parallel"]["times_tried"] == 3
    assert by_approach["parallel"]["successes"] == 2
    assert abs(by_approach["parallel"]["success_pct"] - 66.7) < 0.1
    assert by_approach["sequential"]["times_tried"] == 2
    assert by_approach["sequential"]["successes"] == 0
    assert by_approach["sequential"]["success_pct"] == 0.0


def test_best_approaches_sorted_by_success(tmp_path):
    db = tmp_path / "test.db"
    for _ in range(3):
        insert_approach("core:build", "approach_a", "success", db_path=db)
    for _ in range(2):
        insert_approach("core:build", "approach_b", "success", db_path=db)
    insert_approach("core:build", "approach_b", "failure", db_path=db)
    for _ in range(2):
        insert_approach("core:build", "approach_c", "failure", db_path=db)

    best = get_best_approaches("core:build", limit=3, db_path=db)
    assert len(best) == 3
    assert best[0]["approach"] == "approach_a"
    assert best[0]["success_pct"] == 100.0
    assert best[2]["approach"] == "approach_c"
    assert best[2]["success_pct"] == 0.0


def test_best_approaches_respects_limit(tmp_path):
    db = tmp_path / "test.db"
    for name in ["a", "b", "c", "d"]:
        for _ in range(2):
            insert_approach("core:build", name, "success", db_path=db)
    best = get_best_approaches("core:build", limit=2, db_path=db)
    assert len(best) == 2


def test_patterns_filter_by_skill(tmp_path):
    db = tmp_path / "test.db"
    for _ in range(2):
        insert_approach("core:build", "method_x", "success", db_path=db)
    for _ in range(2):
        insert_approach("quality:debug", "trace_pipeline", "success", db_path=db)

    build_patterns = get_approach_patterns("core:build", db_path=db)
    debug_patterns = get_approach_patterns("quality:debug", db_path=db)
    all_patterns = get_approach_patterns(db_path=db)

    assert len(build_patterns) == 1
    assert len(debug_patterns) == 1
    assert len(all_patterns) == 2


def test_capture_approach_writes_to_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("lib.studio_db._db_path", lambda: db)
    ok = capture_approach("core:build", "test approach", "success", context="test")
    assert ok is True
    conn = _connect(db)
    row = conn.execute("SELECT * FROM raw_approaches").fetchone()
    conn.close()
    assert row is not None
    assert row["approach"] == "test approach"


def test_capture_approach_fallback_on_bad_db(tmp_path, monkeypatch):
    bad_db = tmp_path / "no_dir" / "bad.db"
    monkeypatch.setattr("lib.studio_db._db_path", lambda: bad_db)
    meta = tmp_path / "meta"
    monkeypatch.setattr("lib.paths.meta_dir", lambda: meta)
    ok = capture_approach("core:build", "fallback test", "success")
    assert ok is True
    log = meta / "approaches.log"
    assert log.exists()
    content = log.read_text(encoding="utf-8")
    assert "approach:core:build" in content
    assert "fallback test" in content


def test_rolling_prune_includes_approaches(tmp_path):
    db = tmp_path / "test.db"
    conn = _connect(db)
    conn.execute(
        "INSERT INTO raw_approaches (skill_id, session_date, approach, outcome, captured_at) "
        "VALUES ('old:skill', '2020-01-01', 'ancient', 'success', '2020-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    pruned = rolling_window_prune(db_path=db)
    assert pruned >= 1
    conn = _connect(db)
    count = conn.execute("SELECT COUNT(*) FROM raw_approaches").fetchone()[0]
    conn.close()
    assert count == 0


def test_graceful_on_bad_db_path(tmp_path):
    bad = tmp_path / "no_such_dir" / "test.db"
    assert insert_approach("x", "y", "z", db_path=bad) is False
    assert get_approach_patterns(db_path=bad) == []
    assert get_best_approaches("x", db_path=bad) == []
