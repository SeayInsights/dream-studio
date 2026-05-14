from __future__ import annotations

import json
import sqlite3

from core.shared_intelligence.lineage_cleanup import (
    correction_hardening_candidates,
    correction_learning_event_rows,
    correction_lineage_status,
    manual_review_lineage_plan,
    quarantined_project_lineage_status,
    raw_skill_telemetry_status,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _create_skill_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE raw_skill_telemetry(
            id INTEGER PRIMARY KEY,
            skill_name TEXT,
            invoked_at TEXT,
            success INTEGER,
            project_id TEXT,
            session_id TEXT,
            event_id TEXT
        );
        CREATE TABLE cor_skill_corrections(
            id INTEGER PRIMARY KEY,
            telemetry_id INTEGER,
            corrected_success INTEGER,
            reason TEXT,
            corrected_at TEXT
        );
        CREATE TABLE skill_invocations(
            invocation_id TEXT PRIMARY KEY,
            project_id TEXT,
            milestone_id TEXT,
            task_id TEXT,
            process_run_id TEXT,
            event_id TEXT,
            skill_id TEXT,
            status TEXT,
            purpose TEXT,
            metadata_json TEXT,
            created_at TEXT
        );
        CREATE TABLE learning_event_records(
            learning_event_id TEXT PRIMARY KEY,
            project_id TEXT,
            milestone_id TEXT,
            task_id TEXT,
            process_run_id TEXT,
            component_type TEXT,
            component_id TEXT,
            event_class TEXT,
            severity TEXT,
            summary TEXT,
            observed_pattern TEXT,
            root_cause TEXT,
            remediation_hint TEXT,
            recurrence_key TEXT,
            promotion_status TEXT,
            source_refs_json TEXT,
            evidence_refs_json TEXT,
            metadata_json TEXT,
            created_at TEXT
        );
        """)


def test_raw_skill_status_requires_correction_migration_before_purge() -> None:
    conn = _conn()
    _create_skill_tables(conn)
    conn.execute(
        "INSERT INTO raw_skill_telemetry(id, skill_name, invoked_at, success) VALUES(1, 'build', '2026-01-01', 1)"
    )
    conn.execute(
        "INSERT INTO skill_invocations(invocation_id, skill_id, status, purpose, metadata_json, created_at) "
        "VALUES('legacy-raw-skill-1', 'build', 'completed', 'legacy raw_skill_telemetry backfill', ?, '2026-01-01')",
        (json.dumps({"source_table": "raw_skill_telemetry", "source_id": 1}),),
    )
    conn.execute(
        "INSERT INTO cor_skill_corrections(id, telemetry_id, corrected_success, reason, corrected_at) "
        "VALUES(7, 1, 0, 'heuristic was wrong', '2026-05-09')"
    )

    status = raw_skill_telemetry_status(conn)

    assert status["mapped_rows"] == 1
    assert status["unmapped_source_ids"] == []
    assert status["classification"] == "requires_correction_migration_first"
    assert status["purge_ready"] is False


def test_correction_rows_generate_learning_events_and_candidates() -> None:
    conn = _conn()
    _create_skill_tables(conn)
    conn.execute(
        "INSERT INTO raw_skill_telemetry(id, skill_name, invoked_at, success, project_id) "
        "VALUES(1, 'build', '2026-01-01', 1, 'dream-studio')"
    )
    for correction_id in range(1, 4):
        conn.execute(
            "INSERT INTO cor_skill_corrections(id, telemetry_id, corrected_success, reason, corrected_at) "
            "VALUES(?, 1, 0, 'heuristic was wrong', ?)",
            (correction_id, f"2026-05-0{correction_id}"),
        )

    events = correction_learning_event_rows(conn)
    candidates = correction_hardening_candidates(events)

    assert len(events) == 3
    assert events[0]["event_class"] == "operator_correction"
    assert "sqlite:cor_skill_corrections:1" in events[0]["source_refs"]
    assert "sqlite:raw_skill_telemetry:1" in events[0]["source_refs"]
    assert events[0]["metadata"]["legacy_correction_id"] == 1
    assert candidates
    assert candidates[0]["hardening_type"] == "recurring_operator_correction"


def test_correction_lineage_status_detects_migrated_rows() -> None:
    conn = _conn()
    _create_skill_tables(conn)
    conn.execute(
        "INSERT INTO cor_skill_corrections(id, telemetry_id, corrected_success, reason, corrected_at) "
        "VALUES(1, 1, 0, '', '2026-05-09')"
    )
    conn.execute(
        "INSERT INTO learning_event_records(learning_event_id, event_class, severity, summary, source_refs_json, metadata_json) "
        "VALUES('legacy-skill-correction-1', 'operator_correction', 'info', 'migrated', ?, ?)",
        (
            json.dumps(["sqlite:cor_skill_corrections:1"]),
            json.dumps({"legacy_correction_id": 1}),
        ),
    )

    status = correction_lineage_status(conn)

    assert status["classification"] == "migrated_then_purge_source"
    assert status["purge_ready"] is True


def test_quarantined_project_dependents_are_purge_ready_when_only_local_refs_exist() -> None:
    conn = _conn()
    conn.executescript("""
        CREATE TABLE reg_projects(project_id TEXT, project_path TEXT, project_name TEXT, project_source TEXT, is_temp INTEGER, status TEXT, deactivation_reason TEXT);
        CREATE TABLE ds_documents(doc_id INTEGER, project_id TEXT, doc_type TEXT);
        CREATE TABLE raw_approaches(id INTEGER, project_id TEXT, skill_id TEXT);
        CREATE TABLE _backup_037_reg_projects(project_id TEXT);
        """)
    conn.execute(
        "INSERT INTO reg_projects(project_id, project_path, is_temp, status) VALUES('proj-1', '/path', 1, 'quarantined')"
    )
    conn.execute(
        "INSERT INTO ds_documents(doc_id, project_id, doc_type) VALUES(1, 'proj-1', 'prd')"
    )
    conn.execute(
        "INSERT INTO raw_approaches(id, project_id, skill_id) VALUES(1, 'proj-1', 'core:build')"
    )
    conn.execute("INSERT INTO _backup_037_reg_projects(project_id) VALUES('proj-1')")

    status = quarantined_project_lineage_status(conn, ("proj-1",))

    assert status["classification"] == "obsolete_purge"
    assert status["purge_ready"] is True
    assert status["active_reference_counts"]["_backup_037_reg_projects"] == 1
    assert status["blocking_reference_counts"] == {}
    assert status["content_inspected"] is False


def test_manual_review_plan_is_not_executable_by_default() -> None:
    conn = _conn()
    _create_skill_tables(conn)
    conn.execute("CREATE TABLE reg_projects(project_id TEXT, is_temp INTEGER, status TEXT)")

    plan = manual_review_lineage_plan(conn)

    assert plan["derived_view"] is True
    assert plan["primary_authority"] is False
    assert plan["execution_authorized"] is False
