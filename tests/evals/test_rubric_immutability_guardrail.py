"""Gate test: runtime rubric-immutability guardrail (WO 58890751).

Verifies check_rubric_write_guardrail() in guardrails/evaluator.py:
  - Write to eval-rubric.yml → guardrail_decisions block row created
  - Non-rubric path → None returned, no DB write
  - event_id is forwarded to the decision row
"""

from __future__ import annotations

import sqlite3


_DDL = """
CREATE TABLE IF NOT EXISTS guardrail_decisions (
    decision_id TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    event_id    TEXT,
    action      TEXT NOT NULL,
    message     TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    metadata    TEXT
)
"""


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(_DDL)
    conn.commit()
    return conn


def test_rubric_write_creates_block_decision():
    """Write to eval-rubric.yml creates a guardrail_decisions block row."""
    from guardrails.evaluator import check_rubric_write_guardrail

    conn = _make_conn()
    decision = check_rubric_write_guardrail(
        "canonical/skills/domains/eval-rubric.yml",
        conn=conn,
    )

    assert decision is not None
    assert decision.action.value == "block"
    assert decision.rule_id == "rubric-immutability-constraint"

    rows = conn.execute("SELECT action, rule_id FROM guardrail_decisions").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "block"
    assert rows[0][1] == "rubric-immutability-constraint"


def test_non_rubric_path_returns_none():
    """A non-rubric path returns None and writes no decision row."""
    from guardrails.evaluator import check_rubric_write_guardrail

    conn = _make_conn()
    decision = check_rubric_write_guardrail("src/some_module.py", conn=conn)

    assert decision is None
    rows = conn.execute("SELECT * FROM guardrail_decisions").fetchall()
    assert rows == []


def test_event_id_forwarded_to_decision_row():
    """event_id passed to the guardrail is stored in the guardrail_decisions row."""
    from guardrails.evaluator import check_rubric_write_guardrail

    conn = _make_conn()
    decision = check_rubric_write_guardrail(
        "canonical/skills/domains/eval-rubric.yml",
        conn=conn,
        event_id="test-event-abc123",
    )

    assert decision is not None
    assert decision.event_id == "test-event-abc123"

    row = conn.execute("SELECT event_id FROM guardrail_decisions").fetchone()
    assert row is not None
    assert row[0] == "test-event-abc123"


def test_none_file_path_returns_none():
    """None file_path returns None without any DB write."""
    from guardrails.evaluator import check_rubric_write_guardrail

    conn = _make_conn()
    decision = check_rubric_write_guardrail(None, conn=conn)

    assert decision is None
    rows = conn.execute("SELECT * FROM guardrail_decisions").fetchall()
    assert rows == []
