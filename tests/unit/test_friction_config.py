"""Tests for eval.friction_threshold resolution order (WO-FRICTION-CONFIG).

Proving gate:
  Layer 1 — env var overrides both ds_config and per-row threshold
  Layer 2 — ds_config row overrides per-row threshold when env var unset
  Layer 3 — per-row threshold (default 3) used when neither env var nor ds_config is set

Also covers ds config set/get/list in core/config/authority.py.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ds_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

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
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_friction_config.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    return p


def _seed_target(db_path: Path, target_id: str, per_row_threshold: int = 3) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO eval_registry"
        " (eval_id, target_id, target_type, friction_threshold)"
        " VALUES (?, ?, 'skill', ?)",
        (target_id, target_id, per_row_threshold),
    )
    # Add a session-failure signal so aggregate has something to flag.
    conn.execute(
        "INSERT INTO raw_sessions (session_id, outcome) VALUES (?, 'failed')",
        (f"sess-{target_id}",),
    )
    conn.execute(
        "INSERT INTO raw_skill_telemetry (skill_name, session_id) VALUES (?, ?)",
        (target_id, f"sess-{target_id}"),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# core/config/authority.py: set / get / list
# ---------------------------------------------------------------------------


def test_set_and_get_config_value(db_path: Path) -> None:
    from core.config.authority import get_config_value, set_config_value

    set_config_value("eval.friction_threshold", "5", db_path)
    assert get_config_value("eval.friction_threshold", db_path) == "5"


def test_get_config_value_missing_returns_none(db_path: Path) -> None:
    from core.config.authority import get_config_value

    assert get_config_value("nonexistent.key", db_path) is None


def test_set_config_value_upserts(db_path: Path) -> None:
    from core.config.authority import get_config_value, set_config_value

    set_config_value("eval.friction_threshold", "5", db_path)
    set_config_value("eval.friction_threshold", "7", db_path)
    assert get_config_value("eval.friction_threshold", db_path) == "7"


def test_list_config_returns_all_rows(db_path: Path) -> None:
    from core.config.authority import list_config, set_config_value

    set_config_value("eval.friction_threshold", "4", db_path)
    set_config_value("other.key", "hello", db_path)
    rows = list_config(db_path)
    keys = {r["key"] for r in rows}
    assert "eval.friction_threshold" in keys
    assert "other.key" in keys


# ---------------------------------------------------------------------------
# aggregate_friction_signals: Layer 3 — per-row threshold (no env, no ds_config)
# ---------------------------------------------------------------------------


def test_per_row_threshold_respected(db_path: Path) -> None:
    """With no env var or ds_config, per-row threshold=2 flags after 2 signals."""
    from core.eval.friction import aggregate_friction_signals

    _seed_target(db_path, "skill-A", per_row_threshold=2)

    env = {k: v for k, v in os.environ.items() if k != "DREAM_STUDIO_FRICTION_THRESHOLD"}
    import unittest.mock as mock

    with mock.patch.dict(os.environ, env, clear=True):
        aggregate_friction_signals(db_path=db_path)  # signal count → 1, flag not set
        result = aggregate_friction_signals(db_path=db_path)  # signal count → 2, flag set

    assert result["ok"] is True
    assert result["effective_threshold"] == "per-row"
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT friction_flag, friction_signal_count FROM eval_registry WHERE target_id=?",
        ("skill-A",),
    ).fetchone()
    conn.close()
    assert row[0] == 1
    assert row[1] == 2


# ---------------------------------------------------------------------------
# aggregate_friction_signals: Layer 2 — ds_config overrides per-row
# ---------------------------------------------------------------------------


def test_ds_config_threshold_overrides_per_row(db_path: Path) -> None:
    """ds_config eval.friction_threshold=1 overrides per-row=3; flags on first signal."""
    from core.config.authority import set_config_value
    from core.eval.friction import aggregate_friction_signals

    set_config_value("eval.friction_threshold", "1", db_path)
    _seed_target(db_path, "skill-B", per_row_threshold=3)

    env = {k: v for k, v in os.environ.items() if k != "DREAM_STUDIO_FRICTION_THRESHOLD"}
    import unittest.mock as mock

    with mock.patch.dict(os.environ, env, clear=True):
        result = aggregate_friction_signals(db_path=db_path)

    assert result["ok"] is True
    assert result["effective_threshold"] == 1
    conn = sqlite3.connect(str(db_path))
    flag = conn.execute(
        "SELECT friction_flag FROM eval_registry WHERE target_id=?", ("skill-B",)
    ).fetchone()[0]
    conn.close()
    assert flag == 1


# ---------------------------------------------------------------------------
# aggregate_friction_signals: Layer 1 — env var overrides ds_config
# ---------------------------------------------------------------------------


def test_env_var_overrides_ds_config(db_path: Path) -> None:
    """DREAM_STUDIO_FRICTION_THRESHOLD=1 overrides ds_config=99; flags on first signal."""
    from core.config.authority import set_config_value
    from core.eval.friction import aggregate_friction_signals

    set_config_value("eval.friction_threshold", "99", db_path)
    _seed_target(db_path, "skill-C", per_row_threshold=99)

    import unittest.mock as mock

    env_override = {"DREAM_STUDIO_FRICTION_THRESHOLD": "1"}
    with mock.patch.dict(os.environ, env_override):
        result = aggregate_friction_signals(db_path=db_path)

    assert result["ok"] is True
    assert result["effective_threshold"] == 1
    conn = sqlite3.connect(str(db_path))
    flag = conn.execute(
        "SELECT friction_flag FROM eval_registry WHERE target_id=?", ("skill-C",)
    ).fetchone()[0]
    conn.close()
    assert flag == 1
