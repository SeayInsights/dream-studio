"""WO-DBA-EVAL-DECISION gate tests.

Covers migration 134 (business_work_orders verify columns), migration 135
(eval/decision history backfill into business_canonical_events), the live
event emission paths (verify verdicts, decisions, eval runs), and the
event-type routing registry entries.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_135 = (
    REPO_ROOT / "core" / "event_store" / "migrations" / "135_backfill_eval_decision_events.sql"
)

WO_ID = "abcd1234-0000-0000-0000-000000000001"
PROJECT_ID = "11111111-0000-0000-0000-000000000001"


@pytest.fixture
def migrated_db(tmp_path):
    """Fresh DB with the full migration chain applied (134/135 included)."""
    from core.config.sqlite_bootstrap import run_migrations

    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(db_path)
    run_migrations(conn, apply_unreleased=True)
    conn.commit()
    return conn, db_path


def _seed_work_order(conn) -> None:
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, status, created_at)"
        " VALUES (?, ?, 'mile-1', 'Test WO', 'in_progress', '2026-01-01T00:00:00Z')",
        (WO_ID, PROJECT_ID),
    )
    conn.commit()


def _spool_events(spool_root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_root.rglob("*.json"))]


class TestMigration134VerifyColumns:
    def test_verify_columns_exist(self, migrated_db):
        conn, _ = migrated_db
        cols = {row[1] for row in conn.execute("PRAGMA table_info(business_work_orders)")}
        assert {"verify_status", "verify_score", "verified_at"} <= cols


class TestMigration135Backfill:
    def _seed_history(self, conn) -> None:
        _seed_work_order(conn)
        conn.execute(
            "INSERT INTO ds_eval_runs"
            " (run_id, eval_id, started_at, completed_at, event_score, behavior_score,"
            "  total_score, passed, failure_reasons, run_mode)"
            " VALUES ('run-verify-1', ?, '2026-01-02T00:00:00Z', '2026-01-02T00:01:00Z',"
            "  0.9, 0.8, 0.85, 1, '[]', 'fixture')",
            (f"work_order_verify:{WO_ID[:8]}",),
        )
        conn.execute(
            "INSERT INTO ds_eval_runs"
            " (run_id, eval_id, started_at, completed_at, total_score, passed,"
            "  failure_reasons, run_mode)"
            " VALUES ('run-live-1', 'skill:ds-core', '2026-01-03T00:00:00Z',"
            "  '2026-01-03T00:01:00Z', 0.7, 1, '[]', 'live')",
        )
        conn.execute(
            "INSERT INTO ds_eval_runs"
            " (run_id, eval_id, started_at, completed_at, passed, failure_reasons, run_mode)"
            " VALUES ('run-outcome-1', ?, '2026-01-04T00:00:00Z', '2026-01-04T00:01:00Z',"
            "  0, '[\"symptom persists\"]', 'outcome')",
            (f"outcome:{WO_ID[:8]}",),
        )
        conn.execute(
            "INSERT INTO hook_eval_runs"
            " (run_id, hook_id, eval_type, passed, score, failure_reasons, created_at)"
            " VALUES ('run-hook-1', 'on-edit-dispatch', 'guardrail', 1, 1.0, '[]',"
            "  '2026-01-05T00:00:00Z')",
        )
        conn.execute(
            "INSERT INTO decision_log"
            " (decision_id, decision_type, context, outcome, reasoning, confidence,"
            "  policy_applied, source_subsystem, timestamp)"
            " VALUES ('dec-1', 'ttl.assignment', '{}', '\"7d\"', '{}', 0.9,"
            "  'ttl-policy-v1', 'research', '2026-01-06T00:00:00Z')",
        )
        conn.execute(
            "INSERT INTO decision_event_link (decision_id, event_id, relation_type)"
            " VALUES ('dec-1', 'evt-999', 'triggered')",
        )
        conn.commit()

    def _apply_backfill(self, conn) -> None:
        conn.executescript(MIGRATION_135.read_text(encoding="utf-8"))
        conn.commit()

    def test_backfill_produces_expected_events(self, migrated_db):
        conn, _ = migrated_db
        self._seed_history(conn)
        self._apply_backfill(conn)

        row = conn.execute(
            "SELECT work_order_id, project_id, payload FROM business_canonical_events"
            " WHERE event_type = 'work_order.verified'"
            " AND event_id = 'backfill-135-evalrun-run-verify-1'"
        ).fetchone()
        assert row is not None
        assert row[0] == WO_ID  # short-id join resolved the full work_order_id
        assert row[1] == PROJECT_ID
        payload = json.loads(row[2])
        assert payload["composite_score"] == 0.85 and payload["passed"] == 1

        eval_ids = {
            json.loads(r[0])["eval_id"]
            for r in conn.execute(
                "SELECT payload FROM business_canonical_events"
                " WHERE event_type = 'eval.run.completed'"
            )
        }
        assert {"skill:ds-core", f"outcome:{WO_ID[:8]}", "hook:on-edit-dispatch"} <= eval_ids

        outcome_row = conn.execute(
            "SELECT work_order_id FROM business_canonical_events"
            " WHERE event_id = 'backfill-135-evalrun-run-outcome-1'"
        ).fetchone()
        assert outcome_row[0] == WO_ID

        dec = conn.execute(
            "SELECT payload FROM business_canonical_events"
            " WHERE event_type = 'decision.recorded'"
            " AND event_id = 'backfill-135-decision-dec-1'"
        ).fetchone()
        payload = json.loads(dec[0])
        assert payload["policy_applied"] == "ttl-policy-v1"
        assert payload["triggered_event_id"] == "evt-999"

    def test_backfill_is_idempotent(self, migrated_db):
        conn, _ = migrated_db
        self._seed_history(conn)
        self._apply_backfill(conn)
        before = conn.execute("SELECT COUNT(*) FROM business_canonical_events").fetchone()[0]
        self._apply_backfill(conn)
        after = conn.execute("SELECT COUNT(*) FROM business_canonical_events").fetchone()[0]
        assert before == after


class TestVerifyVerdictPersistence:
    def test_write_eval_run_updates_wo_and_emits_event(self, migrated_db, tmp_path, monkeypatch):
        from core.work_orders.verify import _write_eval_run

        conn, _ = migrated_db
        _seed_work_order(conn)
        spool_root = tmp_path / "spool"
        monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))

        scores = {
            "completion_score": 1.0,
            "correctness_score": 0.9,
            "quality_score": 0.8,
            "composite_score": 0.93,
        }
        _write_eval_run(
            conn,
            work_order_id=WO_ID,
            scores=scores,
            passed=True,
            failure_reasons=[],
            started_at="2026-01-07T00:00:00Z",
            completed_at="2026-01-07T00:05:00Z",
        )
        conn.commit()

        row = conn.execute(
            "SELECT verify_status, verify_score, verified_at FROM business_work_orders"
            " WHERE work_order_id = ?",
            (WO_ID,),
        ).fetchone()
        assert row == ("passed", 0.93, "2026-01-07T00:05:00Z")

        events = _spool_events(spool_root)
        verified = [e for e in events if e["event_type"] == "work_order.verified"]
        assert len(verified) == 1
        assert verified[0]["payload"]["work_order_id"] == WO_ID
        assert verified[0]["trace"]["work_order_id"] == WO_ID

    def test_unreviewable_status_persisted(self, migrated_db, tmp_path, monkeypatch):
        from core.work_orders.verify import _write_eval_run

        conn, _ = migrated_db
        _seed_work_order(conn)
        monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool"))

        zero = {
            k: 0.0
            for k in ("completion_score", "correctness_score", "quality_score", "composite_score")
        }
        _write_eval_run(
            conn,
            work_order_id=WO_ID,
            scores=zero,
            passed=False,
            failure_reasons=["unreviewable_no_commits_found"],
            started_at="2026-01-07T00:00:00Z",
            completed_at="2026-01-07T00:05:00Z",
            status="unreviewable",
        )
        status = conn.execute(
            "SELECT verify_status FROM business_work_orders WHERE work_order_id = ?",
            (WO_ID,),
        ).fetchone()[0]
        assert status == "unreviewable"


class TestDecisionEventEmission:
    def test_emit_decision_event_writes_envelope(self, tmp_path, monkeypatch):
        from core.decisions.emitter import _emit_decision_event
        from core.decisions.schema import Decision

        spool_root = tmp_path / "spool"
        monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))

        decision = Decision(
            decision_id=str(uuid.uuid4()),
            decision_type="ttl.assignment",
            context={"project_id": PROJECT_ID},
            outcome="7d",
            reasoning={"rationale": "default policy"},
            confidence=0.9,
            policy_applied="ttl-policy-v1",
            timestamp="2026-01-08T00:00:00Z",
            source_subsystem="research",
        )
        _emit_decision_event(decision, "evt-123")

        events = _spool_events(spool_root)
        assert len(events) == 1
        evt = events[0]
        assert evt["event_type"] == "decision.recorded"
        assert evt["payload"]["decision_id"] == decision.decision_id
        assert evt["payload"]["triggered_event_id"] == "evt-123"
        assert evt["trace"]["project_id"] == PROJECT_ID


class TestEvalRunEventEmission:
    def test_emit_eval_run_event(self, tmp_path, monkeypatch):
        from core.eval.events import emit_eval_run_event

        spool_root = tmp_path / "spool"
        monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))

        emit_eval_run_event(
            {"eval_id": "outcome:abcd1234", "passed": True, "run_mode": "outcome"},
            work_order_id=WO_ID,
        )
        events = _spool_events(spool_root)
        assert len(events) == 1
        assert events[0]["event_type"] == "eval.run.completed"
        assert events[0]["trace"]["work_order_id"] == WO_ID
        assert events[0]["schema_version"] == 1


class TestEventTypeRegistration:
    def test_event_types_registered(self):
        from canonical.events.types import ALL_EVENT_TYPES

        assert {"work_order.verified", "eval.run.completed", "decision.recorded"} <= ALL_EVENT_TYPES

    def test_routing_registry_routes_to_business(self):
        from config.event_type_registry import get_routes, is_registered

        for event_type in ("work_order.verified", "eval.run.completed", "decision.recorded"):
            assert is_registered(event_type), event_type
            assert "business" in get_routes(event_type), event_type
