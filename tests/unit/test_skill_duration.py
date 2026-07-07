"""Tests for WO-CAPTURE-SKILL-DURATION — derived skill execution duration.

Three tests:
  T1 - test_skill_duration_available_per_invocation: seed paired execution.started /
       execution.completed events and assert the derivation returns the correct
       duration per invocation, excluding unpaired events.
  T2 - test_skills_duration_charts_render: read dashboard.html and assert the
       avg-duration + execution-time-distribution charts have a real data path.
  T3 - test_end_to_end: derivation + read path produce non-zero avg duration for
       a seeded skill in an in-memory DB.
"""

from __future__ import annotations

from tests.dashboard_source import dashboard_source

import sqlite3
import uuid
from datetime import datetime, timedelta, UTC
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DASHBOARD_HTML = REPO_ROOT / "projections/frontend/dashboard.html"

# Anchor event timestamps relative to now so they remain inside any days=N
# query window regardless of wall-clock date.
_BASE = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _bootstrap_minimal(conn: sqlite3.Connection) -> None:
    """Create the execution_events table in a fresh in-memory connection."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_events (
            event_id        TEXT PRIMARY KEY,
            event_type      TEXT NOT NULL,
            event_name      TEXT NOT NULL,
            project_id      TEXT,
            milestone_id    TEXT,
            task_id         TEXT,
            process_run_id  TEXT,
            parent_event_id TEXT,
            actor_type      TEXT,
            actor_id        TEXT,
            agent_id        TEXT,
            skill_id        TEXT,
            workflow_id     TEXT,
            hook_id         TEXT,
            tool_id         TEXT,
            model_id        TEXT,
            adapter_id      TEXT,
            source_refs_json    TEXT NOT NULL DEFAULT '[]',
            evidence_refs_json  TEXT NOT NULL DEFAULT '[]',
            metadata_json       TEXT NOT NULL DEFAULT '{}',
            outcome_status  TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)
    conn.commit()


def _insert_event(
    conn: sqlite3.Connection,
    event_type: str,
    event_name: str,
    process_run_id: str,
    skill_id: str | None = None,
    outcome_status: str | None = None,
    created_at: str | None = None,
) -> str:
    eid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO execution_events
            (event_id, event_type, event_name, process_run_id,
             skill_id, outcome_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?,
                COALESCE(?, datetime('now')))
        """,
        (eid, event_type, event_name, process_run_id, skill_id, outcome_status, created_at),
    )
    return eid


# ─────────────────────────────────────────────────────────────────────────────
# WO-CAPTURE-COMPLETENESS T4 acceptance check (named node-id):
# derived skill duration is available (non-zero) end to end.
# ─────────────────────────────────────────────────────────────────────────────


def test_skill_duration_available() -> None:
    """WO-CAPTURE-COMPLETENESS T4 AC: per-skill execution duration is available
    and non-zero, derived from paired execution.started/completed events.

    Asserts both layers used by the dashboard:
    - skill_usage_sql() yields a non-NULL execution_time_s for a paired run;
    - SkillCollector.collect() surfaces a >0 avg_exec_time_s for that skill.
    """
    import os
    import tempfile

    from core.config.sqlite_bootstrap import bootstrap_database
    from projections.core.collectors.authority_sources import skill_usage_sql
    from projections.core.collectors.skill_collector import SkillCollector

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        bootstrap_database(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        run_id = str(uuid.uuid4())
        _insert_event(
            conn,
            "skill.invoked",
            "skill.invoked",
            run_id,
            skill_id="ds-workorder",
            outcome_status="completed",
            created_at=f"{_BASE} 08:00:00",
        )
        _insert_event(
            conn, "execution.started", "execution.started", run_id, created_at=f"{_BASE} 08:00:00"
        )
        _insert_event(
            conn,
            "execution.completed",
            "execution.completed",
            run_id,
            created_at=f"{_BASE} 08:00:45",
        )
        conn.commit()

        sql = skill_usage_sql(conn)
        assert sql is not None, "skill_usage_sql must derive durations when events exist"
        row = conn.execute(
            f"SELECT execution_time_s FROM ({sql}) t WHERE session_id = ?", (run_id,)
        ).fetchone()
        assert row is not None and row["execution_time_s"] is not None
        assert abs(row["execution_time_s"] - 45.0) < 0.01, "paired run must derive ~45 s"
        conn.close()

        result = SkillCollector(db_path).collect(days=3650)
        by_skill = result.get("by_skill", {})
        assert "ds-workorder" in by_skill, "seeded skill must surface in the collector"
        avg_s = by_skill["ds-workorder"]["avg_exec_time_s"]
        assert (
            avg_s is not None and avg_s > 0
        ), f"skill duration must be available (>0), got {avg_s}"
    finally:
        os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# T1 — derivation returns correct duration, excludes unpaired events
# ─────────────────────────────────────────────────────────────────────────────


def test_skill_duration_available_per_invocation() -> None:
    """T1: paired started/completed events yield correct duration; unpaired → NULL."""
    from projections.core.collectors.authority_sources import skill_usage_sql

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _bootstrap_minimal(conn)

    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())

    # Run A — fully paired: started at T0, completed 30 s later
    _insert_event(
        conn,
        "skill.invoked",
        "skill.invoked",
        run_a,
        skill_id="ds-core",
        outcome_status="completed",
        created_at=f"{_BASE} 10:00:00",
    )
    _insert_event(
        conn,
        "execution.started",
        "execution.started",
        run_a,
        created_at=f"{_BASE} 10:00:00",
    )
    _insert_event(
        conn,
        "execution.completed",
        "execution.completed",
        run_a,
        created_at=f"{_BASE} 10:00:30",
    )

    # Run B — invocation only (no started/completed) → NULL duration
    _insert_event(
        conn,
        "skill.invoked",
        "skill.invoked",
        run_b,
        skill_id="ds-core",
        outcome_status="completed",
        created_at=f"{_BASE} 11:00:00",
    )

    conn.commit()

    sql = skill_usage_sql(conn)
    assert sql is not None, "skill_usage_sql must return a non-None subquery when events exist"

    rows = conn.execute(
        f"SELECT session_id, execution_time_s FROM ({sql}) t ORDER BY invoked_at ASC"
    ).fetchall()

    assert len(rows) == 2, f"Expected 2 invocation rows, got {len(rows)}"

    paired_row = next(r for r in rows if r["session_id"] == run_a)
    duration_s = paired_row["execution_time_s"]
    assert duration_s is not None, "Paired invocation must have a non-NULL execution_time_s"
    assert abs(duration_s - 30.0) < 0.01, f"Expected ~30 s duration for run_a, got {duration_s}"

    unpaired_row = next(r for r in rows if r["session_id"] == run_b)
    assert (
        unpaired_row["execution_time_s"] is None
    ), "Unpaired invocation (no started/completed events) must yield NULL execution_time_s"

    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# T2 — dashboard.html avg-duration + distribution chart have a real data path
# ─────────────────────────────────────────────────────────────────────────────


def test_skills_duration_charts_render() -> None:
    """T2: dashboard.html wires avg-duration and distribution chart from leaderboard data."""
    text = dashboard_source()

    # skills-avg-duration element is populated from avg_duration_minutes (not hardcoded 0)
    assert "skills-avg-duration" in text, "skills-avg-duration element must exist in dashboard.html"
    assert (
        "avg_duration_minutes" in text
    ), "avg_duration_minutes must appear in dashboard.html (data path from API)"
    # The summary function must use the value, not a literal zero
    summary_fn_start = text.find("function updateSkillsSummary")
    summary_fn_end = text.find("\n        function ", summary_fn_start + 1)
    if summary_fn_end < 0:
        summary_fn_end = text.find("\n        async function ", summary_fn_start + 1)
    summary_body = text[summary_fn_start:summary_fn_end] if summary_fn_start >= 0 else ""
    assert (
        "avg_duration_minutes" in summary_body or "avgDuration" in summary_body
    ), "updateSkillsSummary must read avg_duration_minutes from data, not a literal zero"

    # Execution time distribution chart must reference avg_duration_minutes (Avg dataset)
    chart_fn_start = text.find("async function initSkillExecutionTimeChart")
    chart_fn_end = text.find("\n        async function ", chart_fn_start + 1)
    if chart_fn_end < 0:
        chart_fn_end = text.find("\n        function ", chart_fn_start + 1)
    chart_body = text[chart_fn_start:chart_fn_end] if chart_fn_start >= 0 else ""
    assert (
        "avg_duration_minutes" in chart_body
    ), "initSkillExecutionTimeChart must map avg_duration_minutes from leaderboard entries"
    assert (
        "min_duration_minutes" in chart_body
    ), "initSkillExecutionTimeChart must map min_duration_minutes (Min dataset)"
    assert (
        "max_duration_minutes" in chart_body
    ), "initSkillExecutionTimeChart must map max_duration_minutes (Max dataset)"

    # The chart must have an honest empty-state (not just a blank canvas)
    assert (
        "No execution time data" in chart_body or "No execution time data yet" in text
    ), "initSkillExecutionTimeChart must show a user-facing empty-state when data is absent"


# ─────────────────────────────────────────────────────────────────────────────
# T3 — end-to-end: derivation + read path produce non-zero avg for seeded skill
# ─────────────────────────────────────────────────────────────────────────────


def test_end_to_end() -> None:
    """T3: SkillCollector.collect() returns non-zero avg_exec_time_s for a seeded skill."""
    import os
    import tempfile

    from core.config.sqlite_bootstrap import bootstrap_database
    from projections.core.collectors.skill_collector import SkillCollector

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        bootstrap_database(db_path)

        conn = sqlite3.connect(db_path)
        run_id = str(uuid.uuid4())

        # Seed a paired skill invocation with 60 s duration
        _insert_event(
            conn,
            "skill.invoked",
            "skill.invoked",
            run_id,
            skill_id="ds-quality",
            outcome_status="completed",
            created_at=f"{_BASE} 09:00:00",
        )
        _insert_event(
            conn,
            "execution.started",
            "execution.started",
            run_id,
            created_at=f"{_BASE} 09:00:00",
        )
        _insert_event(
            conn,
            "execution.completed",
            "execution.completed",
            run_id,
            created_at=f"{_BASE} 09:01:00",
        )
        conn.commit()
        conn.close()

        collector = SkillCollector(db_path)
        result = collector.collect(days=3650)

        by_skill = result.get("by_skill", {})
        assert (
            "ds-quality" in by_skill
        ), "ds-quality must appear in by_skill after seeding a skill.invoked event"

        avg_s = by_skill["ds-quality"]["avg_exec_time_s"]
        assert (
            avg_s is not None and avg_s > 0
        ), f"avg_exec_time_s must be > 0 for a paired invocation (60 s expected), got {avg_s}"
        assert abs(avg_s - 60.0) < 0.1, f"Expected avg_exec_time_s ≈ 60.0 s, got {avg_s}"

        min_s = by_skill["ds-quality"]["min_exec_time_s"]
        max_s = by_skill["ds-quality"]["max_exec_time_s"]
        assert min_s is not None and min_s > 0, f"min_exec_time_s must be > 0, got {min_s}"
        assert max_s is not None and max_s > 0, f"max_exec_time_s must be > 0, got {max_s}"
        assert abs(min_s - 60.0) < 0.1, f"min_exec_time_s ≈ 60.0 expected, got {min_s}"
        assert abs(max_s - 60.0) < 0.1, f"max_exec_time_s ≈ 60.0 expected, got {max_s}"

    finally:
        os.unlink(db_path)
