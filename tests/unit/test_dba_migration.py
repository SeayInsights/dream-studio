"""WO-DBA-EVAL-DECISION gate tests.

Covers migration 134 (business_work_orders verify columns) plus the migration
136/139/140/141 drop-family fresh-chain assertions, the live event emission
paths (verify verdicts, decisions, eval runs), and the event-type routing
registry entries.

WO-SQUASH-BASELINE (5fd84891, 2026-07-04) collapsed migrations 001-141 into
142_lean_baseline.sql; the individual migration files no longer exist. Two
classes were removed in that change set because their subject was the
mid-chain mechanics of a since-deleted migration file, not a fresh-chain
schema invariant:
  - TestMigration135Backfill executed 135_backfill_eval_decision_events.sql
    directly (file deleted) and asserted on synthetic backfill events that
    only exist when the chain replays that specific historical seed-then-
    backfill sequence -- a fresh baseline install has no legacy rows to
    backfill in the first place.
  - TestMigration136DropTables seeded pre-136 legacy tables at a
    target_version=134 checkpoint that no longer exists in the squashed
    chain (the baseline is the only migration; there is no way to "stop at
    134"), then asserted the same backfill-derived events. Same removal
    rationale as 135.
The remaining classes' fresh-chain assertions (tables absent, no dangling FK,
no dangling view) hold unchanged against the baseline and were kept; their
sub-tests that checkpointed at a specific pre-142 version (target_version=138/
139/140) were removed for the same reason -- those versions no longer exist.
See tests/unit/test_migration_142_baseline.py for the WO-SQUASH-BASELINE
replacement data-preservation proof.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

WO_ID = "abcd1234-0000-0000-0000-000000000001"
PROJECT_ID = "11111111-0000-0000-0000-000000000001"


@pytest.fixture
def migrated_db(tmp_path):
    """Fresh DB with the full migration chain applied (through the latest release)."""
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


class TestMigration136DropTables:
    """WO-DBA-EVAL-DECISION T4: ds_eval_runs, hook_eval_runs, decision_log, and
    decision_event_link are gone from the fresh baseline schema; their history
    lives on in business_canonical_events (work_order.verified /
    eval.run.completed / decision.recorded) via live spool emission."""

    DROPPED_EVAL_DECISION_TABLES = (
        "ds_eval_runs",
        "hook_eval_runs",
        "decision_log",
        "decision_event_link",
    )

    def test_tables_absent_after_full_chain(self, migrated_db):
        conn, _db_path = migrated_db
        for table in self.DROPPED_EVAL_DECISION_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table,),
            ).fetchone()
            assert row is None, f"{table} should not exist in the fresh baseline schema"


class TestMigration139DropTables:
    """WO-AI-SPINE (work order a0cdd612-4c53-4cda-ab07-f940f8f814d5, AD-5):
    decision_records, outcome_records, and dashboard_attention_items are pure
    duplication of the execution_events row every writer in
    core/telemetry/emitters.py already wrote (0/2/0 production rows)."""

    AI_SPINE_DROPPED_TABLES = (
        "decision_records",
        "outcome_records",
        "dashboard_attention_items",
    )

    def test_tables_absent_after_full_chain(self, migrated_db):
        """After the full migration chain (through 139), the three tables are
        gone from a fresh install."""
        conn, _db_path = migrated_db
        for table in self.AI_SPINE_DROPPED_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table,),
            ).fetchone()
            assert row is None, f"{table} should be dropped by migration 139"

    def test_no_foreign_key_references_the_dropped_tables_in_fresh_schema(self, migrated_db):
        """No table in the fresh baseline schema has a FOREIGN KEY into any of
        the three dropped tables (WO-SQUASH-BASELINE narrowed this from a
        target_version=138 pre-drop checkpoint, which no longer exists post-
        squash, to a fresh-schema absence check — equivalent end state)."""
        conn, _db_path = migrated_db
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        offenders = []
        for table in tables:
            for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                if fk[2] in self.AI_SPINE_DROPPED_TABLES:
                    offenders.append((table, fk[2]))
        assert not offenders, (
            "a table has a FOREIGN KEY into one of the migration-139 dropped "
            f"tables — a rebuild (migration-137 pattern) is needed: {offenders}"
        )

    def test_pragma_foreign_key_check_passes_after_drop(self, migrated_db):
        """Dropping the three tables must not leave any dangling FK violation
        elsewhere in the schema."""
        conn, _db_path = migrated_db
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not violations, f"foreign_key_check violations after migration 139: {violations}"


class TestMigration140DropDerivedState:
    """WO dff23cb0-950f-4607-bb30-e1a353a6f8ba (operator-approved pre-squash
    removal): findings_current_status and sum_skill_summary are pure derived
    state duplicating security_events / raw_skill_telemetry — no independent
    signal of their own."""

    DERIVED_STATE_DROPPED_TABLES = (
        "findings_current_status",
        "sum_skill_summary",
    )

    def test_tables_absent_after_full_chain(self, migrated_db):
        """After the full migration chain (through 140), both tables are gone
        from a fresh install."""
        conn, _db_path = migrated_db
        for table in self.DERIVED_STATE_DROPPED_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table,),
            ).fetchone()
            assert row is None, f"{table} should be dropped by migration 140"

    def test_no_foreign_key_references_the_dropped_tables_in_fresh_schema(self, migrated_db):
        """No table in the fresh baseline schema has a FOREIGN KEY into either
        dropped table (WO-SQUASH-BASELINE narrowed this from a
        target_version=139 pre-drop checkpoint, which no longer exists post-
        squash, to a fresh-schema absence check — equivalent end state)."""
        conn, _db_path = migrated_db
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        offenders = []
        for table in tables:
            for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                if fk[2] in self.DERIVED_STATE_DROPPED_TABLES:
                    offenders.append((table, fk[2]))
        assert not offenders, (
            "a table has a FOREIGN KEY into one of the migration-140 dropped "
            f"tables — a rebuild (migration-137 pattern) is needed: {offenders}"
        )

    def test_pragma_foreign_key_check_passes_after_drop(self, migrated_db):
        """Dropping both tables must not leave any dangling FK violation
        elsewhere in the schema."""
        conn, _db_path = migrated_db
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not violations, f"foreign_key_check violations after migration 140: {violations}"

    def test_vw_security_summary_rebuilt_over_security_events(self, migrated_db):
        """vw_security_summary (migration 112) used to read FROM
        findings_current_status; migration 140 rebuilds it to derive the same
        shape directly from security_events (the migration-118 drop/recreate
        view guard pattern) so it keeps working after the table is dropped."""
        conn, _db_path = migrated_db
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name = 'vw_security_summary'"
        ).fetchone()
        assert row is not None, "vw_security_summary should survive migration 140 (rebuilt)"

        conn.execute("""INSERT INTO security_events
               (event_id, event_kind, project_id, severity, title, file_path,
                line_number, scanner_type, created_at)
               VALUES ('m140-finding-1', 'finding.recorded', 'proj-m140', 'high',
                       'Test finding', 'app.py', 5, 'semgrep', datetime('now'))""")
        conn.commit()
        rows = conn.execute(
            "SELECT finding_id, tool, severity, status FROM vw_security_summary"
            " WHERE finding_id = 'm140-finding-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "open"
        assert rows[0]["severity"] == "high"
        assert rows[0]["tool"] == "semgrep"


class TestMigration141DropWorkflowRawTables:
    """WO 9f47a1a0-11db-4fcb-9d93-d350fd9a5a6f (operator-approved pre-squash
    removal): raw_workflow_runs (2 rows) and raw_workflow_nodes (25 rows) both
    last wrote 2026-05-18 despite daily workflow runs — archive_workflow()
    silently swallowed its own INSERT failures. Replaced by direct spool
    emission of workflow.completed / workflow.node.completed canonical events
    (control/execution/workflow/state.py)."""

    WORKFLOW_RAW_DROPPED_TABLES = (
        "raw_workflow_runs",
        "raw_workflow_nodes",
    )

    def test_tables_absent_after_full_chain(self, migrated_db):
        """After the full migration chain (through 141), both tables are gone
        from a fresh install."""
        conn, _db_path = migrated_db
        for table in self.WORKFLOW_RAW_DROPPED_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (table,),
            ).fetchone()
            assert row is None, f"{table} should be dropped by migration 141"

    def test_no_external_foreign_key_references_the_dropped_tables_in_fresh_schema(
        self, migrated_db
    ):
        """No OTHER table in the fresh baseline schema has a FOREIGN KEY into
        either dropped table (WO-SQUASH-BASELINE narrowed this from a
        target_version=140 pre-drop checkpoint, which no longer exists post-
        squash, to a fresh-schema absence check — equivalent end state).
        raw_workflow_nodes -> raw_workflow_runs is expected (both tables are
        dropped together, so neither exists in the fresh schema either)."""
        conn, _db_path = migrated_db
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        offenders = []
        for table in tables:
            if table == "raw_workflow_nodes":
                continue  # the expected internal FK into raw_workflow_runs
            for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                if fk[2] in self.WORKFLOW_RAW_DROPPED_TABLES:
                    offenders.append((table, fk[2]))
        assert not offenders, (
            "a table has a FOREIGN KEY into one of the migration-141 dropped "
            f"tables — a rebuild (migration-137 pattern) is needed: {offenders}"
        )

    def test_pragma_foreign_key_check_passes_after_drop(self, migrated_db):
        """Dropping both tables must not leave any dangling FK violation
        elsewhere in the schema."""
        conn, _db_path = migrated_db
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not violations, f"foreign_key_check violations after migration 141: {violations}"

    def test_no_view_references_the_dropped_tables(self, migrated_db):
        """No live SQLite VIEW reads FROM either dropped table."""
        conn, _db_path = migrated_db
        conn.row_factory = sqlite3.Row
        views = conn.execute("SELECT sql FROM sqlite_master WHERE type='view'").fetchall()
        offenders = [
            row["sql"]
            for row in views
            if row["sql"] and any(table in row["sql"] for table in self.WORKFLOW_RAW_DROPPED_TABLES)
        ]
        assert not offenders, f"views still reference dropped workflow raw tables: {offenders}"


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


class TestMigration143StaleFk:
    """Migration 143 rebuilds audit_runs without the FK clause that referenced a
    dropped table (activity_log). (capability_route_records was dropped in migration
    147 — WO-SCHEMALEAN — so only the audit_runs half of the 143 fix remains testable.)"""

    def test_dead_fk_clauses_removed_and_inserts_work(self, migrated_db):
        conn, _ = migrated_db
        conn.execute("PRAGMA foreign_keys=ON")

        # audit_runs: no FK parents remain (activity_log FK dropped).
        assert [f[2] for f in conn.execute("PRAGMA foreign_key_list(audit_runs)")] == []

        # The latent bug: inserts used to raise "no such table" at DML time. Now they succeed.
        conn.execute(
            "INSERT INTO audit_runs (audit_id, audit_type, audit_scope, target_id, target_type)"
            " VALUES ('A-143', 'security', 'project', 'p', 'project')"
        )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0] == 1
