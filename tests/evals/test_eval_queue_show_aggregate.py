"""Gate tests: ds eval queue show and aggregate commands (WO 7dc2f344).

Proving gate:
  show-pending:    returns count and rows for pending_rerun=1 entries
  show-empty:      returns count=0 and empty list when no pending reruns
  show-no-table:   returns ok=False when eval_registry table is absent
  aggregate-calls: aggregate_friction_signals called with correct db_path
  aggregate-print: aggregate result is forwarded to _print
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_EVAL_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS eval_registry (
    eval_id TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT 'skill',
    target_id TEXT NOT NULL,
    rubric_score INTEGER,
    last_run_at TEXT,
    last_run_id TEXT,
    baseline_run_id TEXT,
    friction_flag INTEGER NOT NULL DEFAULT 0,
    friction_signal_count INTEGER NOT NULL DEFAULT 0,
    friction_threshold INTEGER NOT NULL DEFAULT 3,
    pending_rerun INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (eval_id, target_id)
);
"""


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "test_queue.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(_EVAL_REGISTRY_DDL)
    conn.commit()
    conn.close()
    return p


@pytest.fixture
def evals_dir(tmp_path):
    d = tmp_path / "evals"
    d.mkdir()
    return d


def _seed_registry(db_path: Path, target_id: str, *, pending_rerun: int = 1) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO eval_registry (eval_id, target_id, pending_rerun)" " VALUES (?, ?, ?)",
        (target_id, target_id, pending_rerun),
    )
    conn.commit()
    conn.close()


def _mock_runtime(db_path: Path) -> MagicMock:
    mock = MagicMock()
    mock.db_path = db_path
    return mock


class TestEvalQueueShow:
    def test_show_returns_pending_rows(self, db_path, evals_dir, capsys):
        """show returns pending_rerun=1 rows with correct count."""
        from interfaces.cli.ds import _eval_queue_dispatch

        _seed_registry(db_path, "skill-a")
        _seed_registry(db_path, "skill-b")
        _seed_registry(db_path, "skill-c", pending_rerun=0)

        args = argparse.Namespace(queue_command="show")
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = _mock_runtime(db_path)
            _eval_queue_dispatch(args, evals_dir=evals_dir)

        out = json.loads(capsys.readouterr().out)
        assert out["count"] == 2
        target_ids = {r["target_id"] for r in out["pending_rerun"]}
        assert target_ids == {"skill-a", "skill-b"}

    def test_show_empty_when_no_pending(self, db_path, evals_dir, capsys):
        """show returns count=0 and empty list when no pending reruns."""
        from interfaces.cli.ds import _eval_queue_dispatch

        _seed_registry(db_path, "skill-a", pending_rerun=0)

        args = argparse.Namespace(queue_command="show")
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = _mock_runtime(db_path)
            _eval_queue_dispatch(args, evals_dir=evals_dir)

        out = json.loads(capsys.readouterr().out)
        assert out["count"] == 0
        assert out["pending_rerun"] == []

    def test_show_error_when_table_missing(self, tmp_path, evals_dir, capsys):
        """show returns ok=False when eval_registry table is absent."""
        from interfaces.cli.ds import _eval_queue_dispatch

        empty_db = tmp_path / "empty.db"
        sqlite3.connect(str(empty_db)).close()

        args = argparse.Namespace(queue_command="show")
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = _mock_runtime(empty_db)
            _eval_queue_dispatch(args, evals_dir=evals_dir)

        out = json.loads(capsys.readouterr().out)
        assert out["ok"] is False
        assert "eval_registry" in out["error"]


class TestEvalQueueAggregate:
    def test_aggregate_calls_friction_with_db_path(self, db_path, evals_dir, capsys):
        """aggregate delegates to aggregate_friction_signals with the db_path."""
        from interfaces.cli.ds import _eval_queue_dispatch

        args = argparse.Namespace(queue_command="aggregate")
        fake_result = {
            "ok": True,
            "sources_checked": 3,
            "new_flags": 0,
            "total_signaled": 0,
            "effective_threshold": 3,
        }
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = _mock_runtime(db_path)
            with patch(
                "core.eval.friction.aggregate_friction_signals",
                return_value=fake_result,
            ) as mock_agg:
                _eval_queue_dispatch(args, evals_dir=evals_dir)

        mock_agg.assert_called_once_with(db_path=db_path)

    def test_aggregate_prints_result(self, db_path, evals_dir, capsys):
        """aggregate result dict is printed as JSON."""
        from interfaces.cli.ds import _eval_queue_dispatch

        args = argparse.Namespace(queue_command="aggregate")
        fake_result = {"ok": True, "new_flags": 2}
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = _mock_runtime(db_path)
            with patch(
                "core.eval.friction.aggregate_friction_signals",
                return_value=fake_result,
            ):
                _eval_queue_dispatch(args, evals_dir=evals_dir)

        out = json.loads(capsys.readouterr().out)
        assert out == fake_result
