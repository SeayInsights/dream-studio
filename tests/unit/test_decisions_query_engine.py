"""Tests for the event-backed decision query engine (WO-DBA-EVAL-DECISION T4).

The entire decision read path was rewritten to query business_canonical_events
(event_type='decision.recorded') with dual payload-shape handling: backfilled
rows (migration 135) carry context/outcome/reasoning as JSON-encoded strings,
live-emitted rows carry native JSON values. Covers get_decisions filters,
explain_decision, trace_event via payload.triggered_event_id, audit_decisions,
and _parse_json_field on both shapes.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

LIVE_PAYLOAD = {
    "decision_id": "dec-live-1",
    "decision_type": "ttl.assignment",
    "context": {"project_id": "proj-1", "topic": "caching"},
    "outcome": {"selected_option": "7d"},
    "reasoning": {"rationale": "default policy"},
    "confidence": 0.9,
    "policy_applied": "ttl-policy-v1",
    "source_subsystem": "research",
    "triggered_event_id": "evt-100",
}

# Backfilled shape: context/outcome/reasoning are JSON-encoded strings
# (decision_log stored them as TEXT columns).
BACKFILL_PAYLOAD = {
    "decision_id": "dec-backfill-1",
    "decision_type": "guardrail.policy_enforcement",
    "context": json.dumps({"rule": "no-secrets"}),
    "outcome": json.dumps("block"),
    "reasoning": json.dumps({"rationale": "matched rule"}),
    "confidence": 0.6,
    "policy_applied": "guardrail-v2",
    "source_subsystem": "guardrails",
    "triggered_event_id": "evt-200",
}


@pytest.fixture
def decisions_db(tmp_path, monkeypatch):
    """Migrated temp DB seeded with one live-shape and one backfill-shape event."""
    from core.config.sqlite_bootstrap import run_migrations
    from core.decisions import query_engine

    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn, apply_unreleased=True)

    for event_id, ts, event_type, payload in [
        ("evt-dec-live", "2026-01-02T00:00:00Z", "decision.recorded", LIVE_PAYLOAD),
        ("evt-dec-backfill", "2026-01-01T00:00:00Z", "decision.recorded", BACKFILL_PAYLOAD),
        # The trigger events the decisions reference (trace_event looks these
        # up in the canonical_events view before resolving decisions).
        ("evt-100", "2026-01-01T23:00:00Z", "task.completed", {"work_order_id": "wo-1"}),
        ("evt-200", "2025-12-31T23:00:00Z", "gate.bypassed", {"work_order_id": "wo-2"}),
    ]:
        conn.execute(
            "INSERT INTO business_canonical_events"
            " (event_id, received_at, event_type, event_timestamp, schema_version,"
            "  trace, payload, severity, source)"
            " VALUES (?, ?, ?, ?, 1, '{}', ?, 'info', 'test')",
            (event_id, ts, event_type, ts, json.dumps(payload)),
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(query_engine, "_connect", lambda: _row_conn(db_path))
    return db_path


def _row_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


class TestParseJsonField:
    def test_native_value_passes_through(self):
        from core.decisions.query_engine import _parse_json_field

        assert _parse_json_field({"a": 1}) == {"a": 1}
        assert _parse_json_field(None) is None

    def test_json_string_parses_one_level(self):
        from core.decisions.query_engine import _parse_json_field

        assert _parse_json_field('{"a": 1}') == {"a": 1}
        assert _parse_json_field('"block"') == "block"

    def test_plain_string_returned_unchanged(self):
        from core.decisions.query_engine import _parse_json_field

        assert _parse_json_field("allow") == "allow"


class TestGetDecisions:
    def test_returns_both_shapes_newest_first(self, decisions_db):
        from core.decisions.query_engine import get_decisions

        decisions = get_decisions()
        assert [d.decision_id for d in decisions] == ["dec-live-1", "dec-backfill-1"]
        # Backfilled JSON-string fields decode to native structures.
        backfill = decisions[1]
        assert backfill.context == {"rule": "no-secrets"}
        assert backfill.outcome == "block"
        assert backfill.reasoning == {"rationale": "matched rule"}

    def test_filters(self, decisions_db):
        from core.decisions.query_engine import get_decisions

        assert [d.decision_id for d in get_decisions(decision_type="ttl.assignment")] == [
            "dec-live-1"
        ]
        assert [d.decision_id for d in get_decisions(subsystem="guardrails")] == ["dec-backfill-1"]
        assert [d.decision_id for d in get_decisions(min_confidence=0.8)] == ["dec-live-1"]
        assert get_decisions(decision_type="nonexistent") == []


class TestExplainDecision:
    def test_explains_live_decision(self, decisions_db):
        from core.decisions.query_engine import explain_decision

        result = explain_decision("dec-live-1")
        assert result["decision"].decision_id == "dec-live-1"
        assert result["decision"].confidence == 0.9
        assert result["policy_applied"] == "ttl-policy-v1"
        # payload.triggered_event_id resolves the linked trigger event
        assert [e["event_id"] for e in result["linked_events"]] == ["evt-100"]
        assert result["linked_events"][0]["relation_type"] == "triggered"

    def test_missing_decision(self, decisions_db):
        from core.decisions.query_engine import explain_decision

        result = explain_decision("no-such-decision")
        assert not result.get("decision") or result.get("error")


class TestTraceEvent:
    def test_finds_decision_by_triggered_event(self, decisions_db):
        from core.decisions.query_engine import trace_event

        result = trace_event("evt-200")
        found = json.dumps(result)
        assert "dec-backfill-1" in found

    def test_unlinked_event_yields_empty(self, decisions_db):
        from core.decisions.query_engine import trace_event

        result = trace_event("evt-never-linked")
        assert "dec-live-1" not in json.dumps(result)


class TestAuditDecisions:
    def test_audit_aggregates_by_type(self, decisions_db):
        from core.decisions.query_engine import audit_decisions

        result = audit_decisions("guardrail.policy_enforcement")
        text = json.dumps(result)
        assert "guardrail.policy_enforcement" in text
        assert result  # non-empty structured response
