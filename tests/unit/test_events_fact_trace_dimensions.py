"""A dimension the emitter resolved must reach the fact table, column or not.

`events_fact` is the read surface the dashboard queries. Its dimension columns
were filled from the canonical tables' own columns, and the two tables do not
carry the same ones: `ai_canonical_events` has no `work_order_id`, `task_id`,
`milestone_id`, `tool_id` or `adapter_id`, and `business_canonical_events` has no
`session_id`, `skill_id`, `agent_id` or `model_id`. Whichever side lacked the
column got a literal NULL.

Token events live in `ai_canonical_events`, so measured across 86,241
`token.consumed` rows: `project_id` arrived at 93% because it IS a column there,
while `work_order_id`, `task_id` and `agent_id` all read 0% -- not because
nothing resolved them, but because nothing carried them across. The emitter
writes them onto the envelope's `trace`; the derive dropped them on the floor.

"What did this work order cost" was unanswerable for that reason alone, and it
would have stayed unanswerable no matter how well attribution was resolved
upstream.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

# noqa: E402 — must follow importorskip; this module imports duckdb transitively.
from core.analytics.duckdb_store import (  # noqa: E402
    derive_events_fact,
    ensure_analytics_schema,
)

# ai_canonical_events as it really is: project_id is a column, work_order_id is not.
_DDL = """
CREATE TABLE ai_canonical_events (
    event_id TEXT, received_at TEXT, event_type TEXT, event_timestamp TEXT,
    schema_version INTEGER, trace TEXT, payload TEXT,
    correlation_id TEXT, project_id TEXT, session_id TEXT, skill_id TEXT,
    workflow_id TEXT, agent_id TEXT, hook_id TEXT, model_id TEXT,
    severity TEXT, source TEXT
);
-- The derive reads BOTH canonical tables. Present and empty here, because this
-- file is about what ai_canonical_events alone can carry.
CREATE TABLE business_canonical_events (
    event_id TEXT, received_at TEXT, event_type TEXT, event_timestamp TEXT,
    schema_version INTEGER, trace TEXT, payload TEXT,
    correlation_id TEXT, project_id TEXT, milestone_id TEXT,
    work_order_id TEXT, task_id TEXT, severity TEXT, source TEXT
);
"""


def _spine(tmp_path: Path, *, trace: str, project_id: str | None) -> Path:
    db = tmp_path / "studio.db"
    con = sqlite3.connect(db)
    con.executescript(_DDL)
    con.execute(
        "INSERT INTO ai_canonical_events"
        " (event_id, event_type, event_timestamp, schema_version, trace, payload,"
        "  project_id, model_id, severity, source)"
        " VALUES ('e1','token.consumed','2026-09-21T00:00:00Z',1,?,?,?,'claude-opus-5','info','test')",
        (trace, '{"input_tokens": 10, "output_tokens": 20}', project_id),
    )
    con.commit()
    con.close()
    return db


def _fact(tmp_path: Path, spine: Path) -> dict:
    conn = duckdb.connect(str(tmp_path / "a.db"))
    ensure_analytics_schema(conn)
    derive_events_fact(conn, spine, full_rebuild=True)
    cols = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='events_fact'"
        ).fetchall()
    ]
    row = conn.execute(f"SELECT {', '.join(cols)} FROM events_fact").fetchone()
    conn.close()
    return dict(zip(cols, row))


def test_a_trace_only_dimension_reaches_the_fact_table(tmp_path):
    """THE LOAD-BEARING CASE. work_order_id is not a column on this table, so
    before the fallback this was NULL and every token cost was unattributable to
    a unit of work."""
    spine = _spine(
        tmp_path,
        trace='{"work_order_id": "wo-123", "task_id": "t-9", "milestone_id": "m-4"}',
        project_id="p-1",
    )
    got = _fact(tmp_path, spine)
    assert got["work_order_id"] == "wo-123"
    assert got["task_id"] == "t-9"
    assert got["milestone_id"] == "m-4"


def test_a_real_column_still_wins_over_the_trace(tmp_path):
    """COALESCE, not replace. The table's own column is the stronger assertion and
    a stale trace copy must never override it."""
    spine = _spine(tmp_path, trace='{"project_id": "from-trace"}', project_id="from-column")
    assert _fact(tmp_path, spine)["project_id"] == "from-column"


def test_the_trace_fills_a_column_that_is_present_but_empty(tmp_path):
    """A column that exists and is NULL is not an assertion, so the trace fills it."""
    spine = _spine(tmp_path, trace='{"project_id": "from-trace"}', project_id=None)
    assert _fact(tmp_path, spine)["project_id"] == "from-trace"


def test_a_dimension_in_neither_place_stays_null(tmp_path):
    """No invention. A dimension nothing resolved must read NULL, not a guess."""
    spine = _spine(tmp_path, trace="{}", project_id="p-1")
    got = _fact(tmp_path, spine)
    assert got["work_order_id"] is None
    assert got["task_id"] is None


def test_a_malformed_trace_does_not_break_the_derive(tmp_path):
    """The derive feeds a dashboard. One unparsable row must not take the pipeline
    down, and it must not fabricate a value either."""
    spine = _spine(tmp_path, trace="not json at all", project_id="p-1")
    got = _fact(tmp_path, spine)
    assert got["project_id"] == "p-1"
    assert got["work_order_id"] is None
