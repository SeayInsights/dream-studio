"""Unit tests for hooks/lib/studio_db.py."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.studio_db import (  # noqa: E402
    _connect, archive_workflow, last_run, run_count,
    import_buffer, rebuild_summaries, rolling_window_prune, skill_correct,
)


# ── 1. Schema creates all tables and the view ─────────────────────────────────

def test_schema_creates_all_tables(tmp_path):
    db = tmp_path / "test.db"
    conn = _connect(db)
    rows = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    conn.close()

    names = {r["name"] for r in rows}
    expected_tables = {
        "raw_workflow_runs",
        "raw_workflow_nodes",
        "raw_skill_telemetry",
        "cor_skill_corrections",
        "sum_skill_summary",
        "log_batch_imports",
    }
    assert expected_tables <= names, f"Missing tables: {expected_tables - names}"
    assert "effective_skill_runs" in names, "View effective_skill_runs not found"


# ── 2. archive_workflow round-trip → last_run ─────────────────────────────────

def test_archive_workflow_round_trip(tmp_path):
    db = tmp_path / "test.db"
    wf = {
        "workflow": "hotfix",
        "yaml_path": "/tmp/hotfix.yaml",
        "status": "completed",
        "started": "2026-01-01T00:00:00+00:00",
        "nodes": {
            "n1": {
                "status": "completed",
                "started_at": None,
                "finished_at": None,
                "duration_s": None,
                "output": None,
            }
        },
    }
    result = archive_workflow("hotfix-123", wf, db_path=db)
    assert result is True

    row = last_run("hotfix", db_path=db)
    assert row is not None
    assert row["status"] == "completed"


# ── 3. last_run returns None for absent workflow ───────────────────────────────

def test_last_run_returns_none_when_absent(tmp_path):
    db = tmp_path / "test.db"
    result = last_run("nonexistent", db_path=db)
    assert result is None


# ── 4. import_buffer is idempotent (same file → second import returns 0) ──────

def test_import_buffer_idempotent(tmp_path):
    db = tmp_path / "test.db"
    buf = tmp_path / "buf.jsonl"
    lines = [
        '{"skill_name": "build", "success": 1, "invoked_at": "2026-01-01T00:00:00+00:00"}',
        '{"skill_name": "plan",  "success": 1, "invoked_at": "2026-01-01T00:00:01+00:00"}',
        '{"skill_name": "think", "success": 0, "invoked_at": "2026-01-01T00:00:02+00:00"}',
    ]
    buf.write_text("\n".join(lines), encoding="utf-8")

    first = import_buffer(buf, db_path=db)
    assert first == 3, f"Expected 3 rows on first import, got {first}"

    second = import_buffer(buf, db_path=db)
    assert second == 0, f"Expected 0 rows on second import (idempotent), got {second}"

    conn = _connect(db)
    count = conn.execute("SELECT COUNT(*) FROM raw_skill_telemetry").fetchone()[0]
    conn.close()
    assert count == 3, f"Expected 3 rows in raw_skill_telemetry, got {count}"


# ── 5. import_buffer logs exactly one batch row ───────────────────────────────

def test_import_buffer_batch_logged(tmp_path):
    db = tmp_path / "test.db"
    buf = tmp_path / "buf.jsonl"
    lines = [
        '{"skill_name": "build", "success": 1, "invoked_at": "2026-01-01T00:00:00+00:00"}',
        '{"skill_name": "plan",  "success": 1, "invoked_at": "2026-01-01T00:00:01+00:00"}',
    ]
    buf.write_text("\n".join(lines), encoding="utf-8")
    import_buffer(buf, db_path=db)

    conn = _connect(db)
    batch_rows = conn.execute("SELECT * FROM log_batch_imports").fetchall()
    conn.close()

    assert len(batch_rows) == 1, f"Expected 1 batch log row, got {len(batch_rows)}"
    assert batch_rows[0]["row_count"] == 2


# ── 6. skill_correct applies via effective_skill_runs view ────────────────────

def test_skill_correct_applies_via_view(tmp_path):
    db = tmp_path / "test.db"
    conn = _connect(db)
    conn.execute(
        "INSERT INTO raw_skill_telemetry(skill_name, invoked_at, success) "
        "VALUES('build', '2026-01-01', 1)"
    )
    conn.commit()
    row_id = conn.execute(
        "SELECT id FROM raw_skill_telemetry WHERE skill_name='build'"
    ).fetchone()["id"]
    conn.close()

    ok = skill_correct(row_id, 0, "heuristic was wrong", db_path=db)
    assert ok is True

    conn = _connect(db)
    view_row = conn.execute(
        "SELECT success, signal_source FROM effective_skill_runs WHERE id=?",
        (row_id,),
    ).fetchone()
    conn.close()

    assert view_row is not None
    assert view_row["success"] == 0
    assert view_row["signal_source"] == "corrected"


# ── 7. rebuild_summaries self-heals corrupted data ────────────────────────────

def test_rebuild_summaries_self_heals(tmp_path):
    db = tmp_path / "test.db"
    buf = tmp_path / "buf.jsonl"
    # Insert 5 rows for 'build' (all success=1) via import_buffer
    lines = [
        json.dumps({
            "skill_name": "build",
            "success": 1,
            "invoked_at": f"2026-01-01T00:00:0{i}+00:00",
        })
        for i in range(5)
    ]
    buf.write_text("\n".join(lines), encoding="utf-8")
    import_buffer(buf, db_path=db)

    rebuild_summaries(db_path=db)

    conn = _connect(db)
    row = conn.execute(
        "SELECT times_used, success_rate FROM sum_skill_summary WHERE skill_name='build'"
    ).fetchone()
    assert row is not None, "Expected a summary row for 'build'"
    assert row["times_used"] == 5
    assert abs(row["success_rate"] - 1.0) < 1e-9

    # Corrupt the summary
    conn.execute(
        "UPDATE sum_skill_summary SET times_used=999 WHERE skill_name='build'"
    )
    conn.commit()
    conn.close()

    # Rebuild should self-heal
    rebuild_summaries(db_path=db)

    conn = _connect(db)
    row2 = conn.execute(
        "SELECT times_used FROM sum_skill_summary WHERE skill_name='build'"
    ).fetchone()
    conn.close()
    assert row2["times_used"] == 5, (
        f"Expected times_used=5 after self-heal, got {row2['times_used']}"
    )


# ── 8. Graceful degradation on bad DB path ────────────────────────────────────

def test_graceful_on_bad_db_path(tmp_path):
    bad = tmp_path / "no_such_dir" / "test.db"

    wf = {
        "workflow": "x",
        "yaml_path": "/x.yaml",
        "status": "done",
        "started": "2026-01-01T00:00:00+00:00",
        "nodes": {},
    }
    assert archive_workflow("run-x", wf, db_path=bad) is False
    assert last_run("x", db_path=bad) is None
    assert run_count("x", db_path=bad) == 0
    assert import_buffer(tmp_path / "nonexistent.jsonl", db_path=bad) == 0
    assert skill_correct(1, 0, db_path=bad) is False
    assert rolling_window_prune(db_path=bad) == 0
