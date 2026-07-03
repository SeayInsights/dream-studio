"""Tests for ds eval registry list/show CLI commands (WO 7ca96641).

ds_eval_runs / hook_eval_runs were dropped in migration 136 (WO-DBA-EVAL-DECISION
T4) — registry list/show now read run history from business_canonical_events
(event_type IN ('eval.run.completed', 'work_order.verified')).
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
CREATE TABLE IF NOT EXISTS business_canonical_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_timestamp TEXT,
    payload TEXT
);
"""


def _insert_event(db_path: Path, event_id: str, event_type: str, payload: dict, ts: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_canonical_events (event_id, event_type, event_timestamp, payload)"
        " VALUES (?, ?, ?, ?)",
        (event_id, event_type, ts, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


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

    def test_list_derives_passed_from_matching_canonical_event(self, registry_db):
        """ds eval registry list resolves "passed" via payload.run_id = last_run_id
        against business_canonical_events (ds_eval_runs/hook_eval_runs joins
        dropped migration 136, WO-DBA-EVAL-DECISION T4)."""
        conn = sqlite3.connect(str(registry_db))
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id, last_run_id)"
            " VALUES (?, 'skill', ?, 'run-1')",
            ("skill-a::skill", "skill-a"),
        )
        conn.commit()
        conn.close()
        _insert_event(
            registry_db,
            "evt-1",
            "eval.run.completed",
            {"run_id": "run-1", "eval_id": "eval_case_1", "passed": True},
            "2026-01-01T00:00:00Z",
        )

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
        assert result["registry"][0]["passed"] == "Y"

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

    def test_show_returns_hook_run_history_from_canonical_events(self, registry_db):
        """ds eval registry show <hook_target> reads history filtered by
        eval_id = 'hook:<target_id>' from business_canonical_events (hook_eval_runs
        dropped migration 136, WO-DBA-EVAL-DECISION T4)."""
        conn = sqlite3.connect(str(registry_db))
        conn.execute(
            "INSERT INTO eval_registry (eval_id, target_type, target_id, rubric_score)"
            " VALUES (?, 'hook', ?, 90)",
            ("on-pulse::hook", "on-pulse"),
        )
        conn.commit()
        conn.close()
        _insert_event(
            registry_db,
            "evt-hook-1",
            "eval.run.completed",
            {
                "run_id": "run-hook-1",
                "eval_id": "hook:on-pulse",
                "eval_type": "guardrail",
                "passed": False,
                "score": 0.75,
                "failure_reasons": ["rule-x"],
            },
            "2026-01-02T00:00:00Z",
        )
        # A non-matching event for a different hook must not leak into the results.
        _insert_event(
            registry_db,
            "evt-hook-2",
            "eval.run.completed",
            {"run_id": "run-hook-2", "eval_id": "hook:other-hook", "passed": True},
            "2026-01-02T00:01:00Z",
        )

        from interfaces.cli.commands.eval import _eval_registry_dispatch

        args = argparse.Namespace(registry_command="show", target_id="on-pulse")
        output = []
        with (
            patch("core.config.database.DatabaseRuntime") as mock_dr,
            patch("builtins.print", side_effect=lambda s: output.append(s)),
        ):
            mock_dr.get_instance.return_value = _mock_runtime(registry_db)
            _eval_registry_dispatch(args, source_root=REPO_ROOT)

        result = json.loads(output[0])
        assert len(result["runs"]) == 1
        run = result["runs"][0]
        assert run["run_id"] == "run-hook-1"
        assert run["passed"] is False
        assert run["score"] == 0.75
        assert run["failure_reasons"] == ["rule-x"]

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


class TestHookEvalRunEventEmission:
    """guardrails.evaluator._write_hook_eval_run emits an eval.run.completed
    canonical event instead of writing hook_eval_runs (dropped migration 136)."""

    def test_write_hook_eval_run_emits_event_on_pass(self, tmp_path, monkeypatch):
        from guardrails.evaluator import _write_hook_eval_run

        spool_root = tmp_path / "spool"
        monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))

        _write_hook_eval_run(hook_id="on-pulse", passed=True, failure_reasons=[])

        events = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_root.rglob("*.json"))
        ]
        assert len(events) == 1
        payload = events[0]["payload"]
        assert events[0]["event_type"] == "eval.run.completed"
        assert payload["eval_id"] == "hook:on-pulse"
        assert payload["passed"] is True
        assert payload["score"] == 1.0

    def test_write_hook_eval_run_records_failure_reasons(self, tmp_path, monkeypatch):
        from guardrails.evaluator import _write_hook_eval_run

        spool_root = tmp_path / "spool"
        monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))

        reasons = ["rule-a violated", "rule-b violated"]
        _write_hook_eval_run(hook_id="on-guard", passed=False, failure_reasons=reasons)

        events = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_root.rglob("*.json"))
        ]
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["passed"] is False
        assert payload["score"] < 1.0
        assert "rule-a violated" in payload["failure_reasons"]
