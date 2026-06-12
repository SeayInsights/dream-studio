"""Gate tests: PostToolUse Write events through the guardrail dispatch pipeline (WO 577b90c3).

Proves that _check_rubric_guardrail() in runtime/hooks/meta/on-edit-dispatch.py
(the dispatch entry point wired from main()) is exercised — NOT check_rubric_write_guardrail
in guardrails/evaluator.py directly, which bypasses the integration point.

Proving gate:
  non-operator: Write event targeting eval-rubric.yml → guardrail_decisions block row created
  operator: same event with is_operator=True → zero rows written, return value is None
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_DISPATCH_PATH = (
    Path(__file__).resolve().parents[2] / "runtime" / "hooks" / "meta" / "on-edit-dispatch.py"
)

_DDL = """
CREATE TABLE IF NOT EXISTS guardrail_decisions (
    decision_id  TEXT PRIMARY KEY,
    rule_id      TEXT NOT NULL,
    event_id     TEXT,
    action       TEXT NOT NULL,
    message      TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    metadata     TEXT
)
"""

_RUBRIC_PATH = "canonical/skills/domains/eval-rubric.yml"


def _load_dispatch():
    spec = importlib.util.spec_from_file_location("on_edit_dispatch_guardrail_test", _DISPATCH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_file_db(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    """Create a file-backed SQLite DB with guardrail_decisions table."""
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_DDL)
    conn.commit()
    return db_path, conn


class TestPostToolUseGuardrailDispatch:
    def test_rubric_write_through_dispatch_creates_block_row(self, tmp_path):
        """Non-operator Write to eval-rubric.yml through dispatch entry point → block row created."""
        mod = _load_dispatch()
        db_path, conn = _make_file_db(tmp_path)
        mod.STATE_DIR = tmp_path

        mod._check_rubric_guardrail(_RUBRIC_PATH, event_id="evt-dispatch-001")
        conn.close()

        verify = sqlite3.connect(str(db_path))
        rows = verify.execute("SELECT action, rule_id FROM guardrail_decisions").fetchall()
        verify.close()

        assert len(rows) == 1, f"Expected 1 block row, got {len(rows)}"
        assert rows[0][0] == "block"
        assert rows[0][1] == "rubric-immutability-constraint"

    def test_operator_session_through_dispatch_creates_no_rows(self, tmp_path):
        """Operator Write to eval-rubric.yml through dispatch entry point → zero rows written."""
        mod = _load_dispatch()
        db_path, conn = _make_file_db(tmp_path)
        mod.STATE_DIR = tmp_path
        conn.close()

        result = mod._check_rubric_guardrail(
            _RUBRIC_PATH, event_id="evt-dispatch-002", is_operator=True
        )

        assert result is None

        verify = sqlite3.connect(str(db_path))
        rows = verify.execute("SELECT * FROM guardrail_decisions").fetchall()
        verify.close()

        assert rows == [], f"Expected zero rows for operator session, got {rows}"
