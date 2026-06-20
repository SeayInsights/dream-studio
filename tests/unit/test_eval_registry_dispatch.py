"""Tests for ds eval registry list/show CLI commands and hook_id write path (WO 7ca96641)."""

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
CREATE TABLE IF NOT EXISTS ds_eval_runs (
    run_id TEXT PRIMARY KEY,
    eval_id TEXT NOT NULL,
    eval_version TEXT NOT NULL DEFAULT '1.0.0',
    started_at TEXT,
    completed_at TEXT,
    model_tested TEXT DEFAULT 'claude-sonnet-4-6',
    total_score REAL,
    passed INTEGER NOT NULL DEFAULT 0,
    failure_reasons JSON,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS hook_eval_runs (
    run_id TEXT PRIMARY KEY,
    hook_id TEXT NOT NULL,
    eval_type TEXT NOT NULL DEFAULT 'guardrail',
    passed INTEGER NOT NULL DEFAULT 0,
    score REAL,
    failure_reasons TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry_db(tmp_path):
    p = tmp_path / "registry_test.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(_EVAL_REGISTRY_DDL)
    conn.commit()
    conn.close()
    return p


def _mock_runtime(db_path: Path):
    mock = MagicMock()
    mock.db_path = db_path
    return mock


class TestEvalRegistryList:
    def test_list_returns_all_entries(self, registry_db):
        """ds eval registry list returns all registry rows."""
        conn = sqlite3.connect(str(registry_db))
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id) VALUES (?, 'skill', ?)",
            ("skill-a::skill", "skill-a"),
        )
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id) VALUES (?, 'hook', ?)",
            ("on-pulse::hook", "on-pulse"),
        )
        conn.commit()
        conn.close()

        from interfaces.cli.commands.eval import _eval_registry_dispatch

        args = argparse.Namespace(registry_command="list", target_type=None)
        output = []
        with (
            patch("core.config.database.DatabaseRuntime") as mock_dr,
            patch("builtins.print", side_effect=lambda s: output.append(s)),
        ):
            mock_dr.get_instance.return_value = _mock_runtime(registry_db)
            _eval_registry_dispatch(args, source_root=REPO_ROOT)

        assert output, "Expected JSON output"
        result = json.loads(output[0])
        assert result["count"] == 2
        ids = [r["target_id"] for r in result["registry"]]
        assert "skill-a" in ids
        assert "on-pulse" in ids

    def test_list_filters_by_target_type(self, registry_db):
        """ds eval registry list --target-type hook returns only hook entries."""
        conn = sqlite3.connect(str(registry_db))
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id) VALUES (?, 'skill', ?)",
            ("skill-a::skill", "skill-a"),
        )
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id) VALUES (?, 'hook', ?)",
            ("on-pulse::hook", "on-pulse"),
        )
        conn.commit()
        conn.close()

        from interfaces.cli.commands.eval import _eval_registry_dispatch

        args = argparse.Namespace(registry_command="list", target_type="hook")
        output = []
        with (
            patch("core.config.database.DatabaseRuntime") as mock_dr,
            patch("builtins.print", side_effect=lambda s: output.append(s)),
        ):
            mock_dr.get_instance.return_value = _mock_runtime(registry_db)
            _eval_registry_dispatch(args, source_root=REPO_ROOT)

        result = json.loads(output[0])
        assert result["count"] == 1
        assert result["registry"][0]["target_type"] == "hook"

    def test_list_returns_empty_registry_when_no_entries(self, registry_db):
        """ds eval registry list on an empty table returns count=0."""
        from interfaces.cli.commands.eval import _eval_registry_dispatch

        args = argparse.Namespace(registry_command="list", target_type=None)
        output = []
        with (
            patch("core.config.database.DatabaseRuntime") as mock_dr,
            patch("builtins.print", side_effect=lambda s: output.append(s)),
        ):
            mock_dr.get_instance.return_value = _mock_runtime(registry_db)
            _eval_registry_dispatch(args, source_root=REPO_ROOT)

        result = json.loads(output[0])
        assert result["count"] == 0
        assert result["registry"] == []


class TestEvalRegistryShow:
    def test_show_returns_entry_and_empty_runs(self, registry_db):
        """ds eval registry show <target_id> returns entry with empty runs list."""
        conn = sqlite3.connect(str(registry_db))
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id, rubric_score) VALUES (?, 'skill', ?, 85)",
            ("my-skill::skill", "my-skill"),
        )
        conn.commit()
        conn.close()

        from interfaces.cli.commands.eval import _eval_registry_dispatch

        args = argparse.Namespace(registry_command="show", target_id="my-skill")
        output = []
        with (
            patch("core.config.database.DatabaseRuntime") as mock_dr,
            patch("builtins.print", side_effect=lambda s: output.append(s)),
        ):
            mock_dr.get_instance.return_value = _mock_runtime(registry_db)
            _eval_registry_dispatch(args, source_root=REPO_ROOT)

        result = json.loads(output[0])
        assert result["target_id"] == "my-skill"
        assert result["target_type"] == "skill"
        assert result["rubric_score"] == 85
        assert result["runs"] == []

    def test_show_returns_error_for_missing_target(self, registry_db):
        """ds eval registry show <unknown> returns ok=False."""
        from interfaces.cli.commands.eval import _eval_registry_dispatch

        args = argparse.Namespace(registry_command="show", target_id="does-not-exist")
        output = []
        with (
            patch("core.config.database.DatabaseRuntime") as mock_dr,
            patch("builtins.print", side_effect=lambda s: output.append(s)),
        ):
            mock_dr.get_instance.return_value = _mock_runtime(registry_db)
            _eval_registry_dispatch(args, source_root=REPO_ROOT)

        result = json.loads(output[0])
        assert result["ok"] is False
        assert "does-not-exist" in result["error"]


class TestHookIdWritePath:
    def test_write_hook_eval_run_inserts_row_on_pass(self, registry_db):
        """_write_hook_eval_run inserts a hook_eval_runs row when passed=True."""
        from guardrails.evaluator import _write_hook_eval_run

        conn = sqlite3.connect(str(registry_db))
        _write_hook_eval_run(hook_id="on-pulse", passed=True, failure_reasons=[], conn=conn)

        row = conn.execute(
            "SELECT hook_id, passed, score FROM hook_eval_runs WHERE hook_id='on-pulse'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "on-pulse"
        assert row[1] == 1
        assert row[2] == 1.0

    def test_write_hook_eval_run_records_failure_reasons(self, registry_db):
        """_write_hook_eval_run stores failure_reasons JSON when passed=False."""
        from guardrails.evaluator import _write_hook_eval_run

        conn = sqlite3.connect(str(registry_db))
        reasons = ["rule-a violated", "rule-b violated"]
        _write_hook_eval_run(hook_id="on-guard", passed=False, failure_reasons=reasons, conn=conn)

        row = conn.execute(
            "SELECT passed, score, failure_reasons FROM hook_eval_runs WHERE hook_id='on-guard'"
        ).fetchone()
        conn.close()

        assert row[0] == 0
        assert row[1] < 1.0
        parsed = json.loads(row[2])
        assert "rule-a violated" in parsed

    def test_write_hook_eval_run_is_noop_on_missing_table(self, tmp_path):
        """_write_hook_eval_run does not raise when hook_eval_runs table is absent."""
        from guardrails.evaluator import _write_hook_eval_run

        empty_db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(empty_db))
        # No hook_eval_runs table — should not raise
        _write_hook_eval_run(hook_id="any-hook", passed=True, failure_reasons=[], conn=conn)
        conn.close()
