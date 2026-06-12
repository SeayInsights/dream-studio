"""Tests for eval queue clear-on-pass behavior (WO 3e1b30de / WO 9a6222ca).

Proving gate:
  clear-on-pass:   friction_flag and pending_rerun both set to 0 after a passing re-run
  no-clear-on-fail: neither column changes when the eval fails
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
    p = tmp_path / "test_eval_queue.db"
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


def _seed_pending(db_path: Path, target_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO eval_registry (eval_id, target_id, friction_flag, pending_rerun)"
        " VALUES (?, ?, 1, 1)",
        (target_id, target_id),
    )
    conn.commit()
    conn.close()


def _read_flags(db_path: Path, target_id: str) -> tuple[int, int]:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT friction_flag, pending_rerun FROM eval_registry WHERE target_id=?",
        (target_id,),
    ).fetchone()
    conn.close()
    return row[0], row[1]


def _write_case_json(evals_dir: Path, target_id: str) -> None:
    data = {
        "eval_id": target_id,
        "version": "1.0.0",
        "description": "Queue clear test case",
        "skill_id": target_id,
        "input_prompt": "test prompt",
        "expected_events": [],
        "fixture_events": [],
    }
    (evals_dir / f"{target_id}.json").write_text(json.dumps(data))


def _make_eval_result(*, passed: bool):
    from core.eval.schema import EvalResult, MatchResult

    return EvalResult(
        eval_id="ignored",
        version="1.0.0",
        passed=passed,
        composite_score=1.0 if passed else 0.4,
        event_score=1.0 if passed else 0.4,
        match_result=MatchResult(
            score=1.0 if passed else 0.4,
            matched_required=0,
            total_required=0,
            negative_violations=[],
            missing_events=[] if passed else ["missing_event"],
            out_of_order=[],
        ),
    )


class TestEvalQueueClearOnPass:
    def test_passing_run_clears_friction_flag_and_pending_rerun(self, db_path, evals_dir):
        """friction_flag=0 and pending_rerun=0 after a passing queue run."""
        from interfaces.cli.ds import _eval_queue_dispatch

        target_id = "test-skill-pass"
        _seed_pending(db_path, target_id)
        _write_case_json(evals_dir, target_id)

        mock_runtime = MagicMock()
        mock_runtime.db_path = db_path

        args = argparse.Namespace(queue_command="run")
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = mock_runtime
            with patch(
                "core.eval.runner.EvalRunner.run_case",
                return_value=_make_eval_result(passed=True),
            ):
                _eval_queue_dispatch(args, evals_dir=evals_dir)

        friction_flag, pending_rerun = _read_flags(db_path, target_id)
        assert friction_flag == 0, "friction_flag must be cleared to 0 after a passing run"
        assert pending_rerun == 0, "pending_rerun must be cleared to 0 after a passing run"

    def test_failing_run_preserves_friction_flag_and_pending_rerun(self, db_path, evals_dir):
        """friction_flag and pending_rerun unchanged after a failing queue run."""
        from interfaces.cli.ds import _eval_queue_dispatch

        target_id = "test-skill-fail"
        _seed_pending(db_path, target_id)
        _write_case_json(evals_dir, target_id)

        mock_runtime = MagicMock()
        mock_runtime.db_path = db_path

        args = argparse.Namespace(queue_command="run")
        with patch("core.config.database.DatabaseRuntime") as mock_dr:
            mock_dr.get_instance.return_value = mock_runtime
            with patch(
                "core.eval.runner.EvalRunner.run_case",
                return_value=_make_eval_result(passed=False),
            ):
                _eval_queue_dispatch(args, evals_dir=evals_dir)

        friction_flag, pending_rerun = _read_flags(db_path, target_id)
        assert friction_flag == 1, "friction_flag must not change on a failing run"
        assert pending_rerun == 1, "pending_rerun must not change on a failing run"
