"""Phase 9C projection service DB path isolation guardrails."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.event_store import studio_db
from projections.core.alerts import alert_evaluator as alert_evaluator_module
from projections.core.alerts import rule_manager as rule_manager_module
from projections.core.alerts.rule_manager import RuleManager
from projections.core.alerts.alert_evaluator import AlertEvaluator
from projections.core.scheduler import storage as storage_module
from projections.core.scheduler.storage import ScheduleStorage
from projections.scoring import engine as risk_engine_module
from projections.scoring.engine import RiskScoringEngine

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]


def _forbid_global_db(*_args, **_kwargs):
    raise AssertionError("explicit db_path code path used a global DB helper")


def test_schedule_storage_honors_explicit_db_path(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_module, "get_connection", _forbid_global_db)
    monkeypatch.setattr(storage_module, "transaction", _forbid_global_db)

    db_path = tmp_path / "schedules.db"
    storage = ScheduleStorage(db_path)
    job_id = storage.save_schedule(
        {
            "name": "Weekly summary",
            "report_type": "summary",
            "schedule": "0 9 * * MON",
            "recipients": ["team@example.com"],
            "format": "pdf",
        }
    )

    schedules = storage.load_schedules()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT job_id, name FROM scheduled_reports").fetchall()

    assert schedules[0]["job_id"] == job_id
    assert rows == [(job_id, "Weekly summary")]


def test_rule_manager_honors_explicit_db_path(monkeypatch, tmp_path):
    monkeypatch.setattr(rule_manager_module, "get_connection", _forbid_global_db)
    monkeypatch.setattr(rule_manager_module, "transaction", _forbid_global_db)

    db_path = tmp_path / "alerts.db"
    manager = RuleManager(str(db_path))
    rule_id = manager.create_rule(
        {
            "rule_name": "High latency",
            "metric_path": "api.latency_p95",
            "condition": "gt",
            "threshold": 500,
            "severity": "warning",
        }
    )

    active_rules = manager.get_active_rules()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT rule_id, rule_name FROM alert_rules").fetchall()

    assert active_rules[0]["rule_id"] == rule_id
    assert rows == [(rule_id, "High latency")]


def test_alert_evaluator_honors_explicit_db_path(monkeypatch, tmp_path):
    monkeypatch.setattr(alert_evaluator_module, "get_connection", _forbid_global_db)
    monkeypatch.setattr(alert_evaluator_module, "transaction", _forbid_global_db)

    db_path = tmp_path / "alerts.db"
    manager = RuleManager(str(db_path))
    rule_id = manager.create_rule(
        {
            "rule_name": "High failure rate",
            "metric_path": "skill.failure_rate",
            "condition": "gt",
            "threshold": 0.25,
            "severity": "critical",
        }
    )

    evaluator = AlertEvaluator(str(db_path))
    triggered = evaluator.evaluate_rules({"skill.failure_rate": 0.5})

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT rule_id, metric_value, severity FROM alert_history").fetchall()

    assert triggered[0]["rule_id"] == rule_id
    assert rows == [(rule_id, 0.5, "critical")]


def test_risk_scoring_engine_reads_explicit_db_path(monkeypatch, tmp_path):
    monkeypatch.setattr(risk_engine_module, "get_connection", _forbid_global_db)
    monkeypatch.setattr(risk_engine_module, "transaction", _forbid_global_db)

    db_path = tmp_path / "risk.db"
    with studio_db._db_transaction(db_path) as conn:
        conn.execute(
            """
            INSERT INTO activity_log (
                activity_type,
                event_timestamp,
                severity,
                stream_type,
                stream_id,
                event_data
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "security.finding",
                "2026-05-10T00:00:00+00:00",
                "warning",
                "security",
                "finding-1",
                json.dumps({"file_path": "app.py"}),
            ),
        )

    engine = RiskScoringEngine(str(db_path))
    events = engine.fetch_unscored_events(limit=10)

    assert len(events) == 1
    assert events[0]["activity_type"] == "security.finding"


def test_risk_scoring_writer_uses_configured_transaction_helper():
    source = (REPO_ROOT / "projections" / "scoring" / "engine.py").read_text(encoding="utf-8")
    emit_source = source.split("def emit_enriched_event", 1)[1]

    assert "with self._transaction() as conn" in emit_source
    assert "with transaction() as conn" not in emit_source
