"""Tests for aggregate_friction_signals() in core/eval/friction.py (WO 8b30fec0).

Proving gate:
  Source (a): session failures on linked skill invocations → target flagged
  Source (b): skill corrections → target flagged
  Source (c): guardrail blocks on hook targets → target flagged
  Threshold:  friction_flag not set until signal_count >= friction_threshold
  Env override: DREAM_STUDIO_FRICTION_THRESHOLD overrides per-row value
  Return shape: ok, sources_checked, new_flags, total_signaled, effective_threshold
  pending_rerun: set to 1 alongside friction_flag when threshold reached
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

_SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS raw_skill_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT,
    session_id TEXT,
    invoked_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_sessions (
    session_id TEXT PRIMARY KEY,
    outcome TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cor_skill_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER,
    corrected_success INTEGER,
    reason TEXT,
    corrected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS guardrail_decisions (
    decision_id TEXT PRIMARY KEY,
    rule_id TEXT,
    event_id TEXT,
    action TEXT,
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "test_friction.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    return p


def _register_skill(db_path: Path, target_id: str, threshold: int = 3) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO eval_registry"
        " (eval_id, target_id, target_type, friction_threshold)"
        " VALUES (?, ?, 'skill', ?)",
        (target_id, target_id, threshold),
    )
    conn.commit()
    conn.close()


def _register_hook(db_path: Path, target_id: str, threshold: int = 3) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO eval_registry"
        " (eval_id, target_id, target_type, friction_threshold)"
        " VALUES (?, ?, 'hook', ?)",
        (target_id, target_id, threshold),
    )
    conn.commit()
    conn.close()


def _read_registry(db_path: Path, target_id: str) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT friction_flag, friction_signal_count, pending_rerun"
        " FROM eval_registry WHERE target_id=?",
        (target_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def _seed_session_failure(db_path: Path, skill_name: str) -> None:
    conn = sqlite3.connect(str(db_path))
    sess_id = f"sess-{skill_name}-fail"
    conn.execute(
        "INSERT OR IGNORE INTO raw_sessions (session_id, outcome) VALUES (?, 'failed')",
        (sess_id,),
    )
    conn.execute(
        "INSERT INTO raw_skill_telemetry (skill_name, session_id) VALUES (?, ?)",
        (skill_name, sess_id),
    )
    conn.commit()
    conn.close()


def _seed_correction(db_path: Path, skill_name: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO raw_skill_telemetry (skill_name, session_id) VALUES (?, 'sess-cor')",
        (skill_name,),
    )
    row = conn.execute(
        "SELECT id FROM raw_skill_telemetry WHERE skill_name=? ORDER BY id DESC LIMIT 1",
        (skill_name,),
    ).fetchone()
    conn.execute(
        "INSERT INTO cor_skill_corrections (telemetry_id, corrected_success) VALUES (?, 0)",
        (row[0],),
    )
    conn.commit()
    conn.close()


def _seed_guardrail_block(db_path: Path, rule_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO guardrail_decisions (decision_id, rule_id, action) VALUES (?, ?, 'block')",
        (f"gd-{rule_id}", rule_id),
    )
    conn.commit()
    conn.close()


# ── Return shape ─────────────────────────────────────────────────────────────


class TestReturnShape:
    def test_ok_field_present(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        result = aggregate_friction_signals(db_path=db_path)
        assert result["ok"] is True

    def test_sources_checked_is_three(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        result = aggregate_friction_signals(db_path=db_path)
        assert result["sources_checked"] == 3

    def test_no_signals_returns_zero_flags(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        result = aggregate_friction_signals(db_path=db_path)
        assert result["new_flags"] == 0
        assert result["total_signaled"] == 0

    def test_effective_threshold_default_is_per_row(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        result = aggregate_friction_signals(db_path=db_path)
        assert result["effective_threshold"] == "per-row"


# ── Source (a): session failures ──────────────────────────────────────────────


class TestSourceA:
    def test_session_failure_increments_signal_count(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:test-a")
        _seed_session_failure(db_path, "ds-quality:test-a")

        result = aggregate_friction_signals(db_path=db_path)

        assert result["total_signaled"] >= 1
        row = _read_registry(db_path, "ds-quality:test-a")
        assert row["friction_signal_count"] == 1

    def test_error_outcome_also_signals(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:test-error")
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT OR IGNORE INTO raw_sessions (session_id, outcome) VALUES ('sess-err', 'error')"
        )
        conn.execute(
            "INSERT INTO raw_skill_telemetry (skill_name, session_id) VALUES (?, 'sess-err')",
            ("ds-quality:test-error",),
        )
        conn.commit()
        conn.close()

        aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "ds-quality:test-error")
        assert row["friction_signal_count"] == 1

    def test_successful_session_does_not_signal(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:test-success")
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT OR IGNORE INTO raw_sessions (session_id, outcome)"
            " VALUES ('sess-ok', 'completed')"
        )
        conn.execute(
            "INSERT INTO raw_skill_telemetry (skill_name, session_id)"
            " VALUES ('ds-quality:test-success', 'sess-ok')",
        )
        conn.commit()
        conn.close()

        aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "ds-quality:test-success")
        assert row["friction_signal_count"] == 0


# ── Source (b): skill corrections ─────────────────────────────────────────────


class TestSourceB:
    def test_correction_increments_signal_count(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:test-b")
        _seed_correction(db_path, "ds-quality:test-b")

        aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "ds-quality:test-b")
        assert row["friction_signal_count"] == 1


# ── Source (c): guardrail blocks ──────────────────────────────────────────────


class TestSourceC:
    def test_guardrail_block_on_hook_target_increments_count(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_hook(db_path, "rubric-immutability")
        _seed_guardrail_block(db_path, "rubric-immutability")

        aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "rubric-immutability")
        assert row["friction_signal_count"] == 1

    def test_allow_action_does_not_signal(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_hook(db_path, "rule4-ingestor")
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO guardrail_decisions (decision_id, rule_id, action)"
            " VALUES ('gd-allow', 'rule4-ingestor', 'allow')"
        )
        conn.commit()
        conn.close()

        aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "rule4-ingestor")
        assert row["friction_signal_count"] == 0

    def test_block_on_unknown_rule_does_not_error(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        # Block for a rule_id that has no eval_registry entry — should not crash
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO guardrail_decisions (decision_id, rule_id, action)"
            " VALUES ('gd-unknown', 'unknown-rule', 'block')"
        )
        conn.commit()
        conn.close()

        result = aggregate_friction_signals(db_path=db_path)
        assert result["ok"] is True


# ── Threshold logic ───────────────────────────────────────────────────────────


class TestThresholdLogic:
    def test_flag_not_set_below_threshold(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:below-thresh", threshold=3)
        _seed_session_failure(db_path, "ds-quality:below-thresh")

        aggregate_friction_signals(db_path=db_path)  # count=1, threshold=3

        row = _read_registry(db_path, "ds-quality:below-thresh")
        assert row["friction_flag"] == 0
        assert row["pending_rerun"] == 0

    def test_flag_set_when_count_reaches_threshold(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:at-thresh", threshold=1)
        _seed_session_failure(db_path, "ds-quality:at-thresh")

        result = aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "ds-quality:at-thresh")
        assert row["friction_flag"] == 1
        assert row["pending_rerun"] == 1
        assert result["new_flags"] >= 1

    def test_pending_rerun_set_alongside_friction_flag(self, db_path):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:pending-check", threshold=1)
        _seed_session_failure(db_path, "ds-quality:pending-check")

        aggregate_friction_signals(db_path=db_path)

        row = _read_registry(db_path, "ds-quality:pending-check")
        assert row["friction_flag"] == row["pending_rerun"], (
            "friction_flag and pending_rerun must be set atomically"
        )


# ── Env var override ──────────────────────────────────────────────────────────


class TestEnvVarOverride:
    def test_env_override_lowers_effective_threshold(self, db_path, monkeypatch):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:env-override", threshold=5)
        _seed_session_failure(db_path, "ds-quality:env-override")

        monkeypatch.setenv("DREAM_STUDIO_FRICTION_THRESHOLD", "1")
        result = aggregate_friction_signals(db_path=db_path)

        assert result["effective_threshold"] == 1
        row = _read_registry(db_path, "ds-quality:env-override")
        assert row["friction_flag"] == 1

    def test_env_override_raises_effective_threshold(self, db_path, monkeypatch):
        from core.eval.friction import aggregate_friction_signals

        _register_skill(db_path, "ds-quality:env-raise", threshold=1)
        _seed_session_failure(db_path, "ds-quality:env-raise")

        monkeypatch.setenv("DREAM_STUDIO_FRICTION_THRESHOLD", "10")
        result = aggregate_friction_signals(db_path=db_path)

        assert result["effective_threshold"] == 10
        row = _read_registry(db_path, "ds-quality:env-raise")
        # count=1 < 10 → flag not set
        assert row["friction_flag"] == 0

    def test_non_numeric_env_falls_back_to_per_row(self, db_path, monkeypatch):
        from core.eval.friction import aggregate_friction_signals

        monkeypatch.setenv("DREAM_STUDIO_FRICTION_THRESHOLD", "not-a-number")
        result = aggregate_friction_signals(db_path=db_path)
        assert result["effective_threshold"] == "per-row"
