from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import run_migrations
from core.upgrade.canonical_event_reconciliation import (
    build_import_plan,
    connect_backup_readonly,
    ensure_import_map_table,
    profile_canonical_events,
    run_reconciliation,
    validate_reconciliation,
)


def _write_backup_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trace JSON NOT NULL,
            severity TEXT NOT NULL,
            payload JSON NOT NULL,
            actor JSON,
            confidence_score REAL,
            source_type TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    rows = [
        (
            "skill-1",
            "raw.migrated.raw_skill_telemetry",
            "2026-05-01T00:00:00Z",
            {"migrated_from": "raw_skill_telemetry"},
            "info",
            {
                "id": 101,
                "skill_name": "ds-core",
                "invoked_at": "2026-05-01T00:00:00Z",
                "success": 1,
                "project_id": "dream-studio",
            },
            None,
            None,
            "raw_table_migration",
        ),
        (
            "hook-duplicate",
            "hook.execution.on_pulse",
            "2026-05-01T00:01:00Z",
            {"source": "hook_executions_migration", "original_id": 2},
            "info",
            {
                "hook_name": "on_pulse",
                "hook_type": "periodic",
                "status": "success",
                "activity_id": 2,
            },
            None,
            None,
            None,
        ),
        (
            "validation-noise",
            "event.validation.failed",
            "2026-05-01T00:02:00Z",
            {"execution_id": "pulse"},
            "high",
            {"invalid_event_type": "execution.completed", "errors": ["bad shape"]},
            None,
            None,
            None,
        ),
        (
            "token-raw",
            "raw.migrated.raw_token_usage",
            "2026-05-01T00:03:00Z",
            {"migrated_from": "raw_token_usage"},
            "info",
            {
                "id": 501,
                "session_id": "session-a",
                "project_id": "dream-studio",
                "skill_name": "ds-core",
                "input_tokens": 1,
                "output_tokens": 2,
                "model": "claude-test",
                "recorded_at": "2026-05-01T00:03:00Z",
            },
            None,
            None,
            "raw_table_migration",
        ),
        (
            "token-manual",
            "telemetry.token_usage",
            "2026-05-01T00:04:00Z",
            {"migrated_from": "canonical_events"},
            "info",
            {"session_id": "session-b", "input_tokens": 1, "output_tokens": 2},
            None,
            None,
            None,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO canonical_events (
            event_id, event_type, timestamp, trace, severity, payload, actor,
            confidence_score, source_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                event_id,
                event_type,
                timestamp,
                json.dumps(trace),
                severity,
                json.dumps(payload),
                json.dumps(actor) if actor else None,
                confidence,
                source_type,
            )
            for (
                event_id,
                event_type,
                timestamp,
                trace,
                severity,
                payload,
                actor,
                confidence,
                source_type,
            ) in rows
        ],
    )
    conn.commit()
    conn.close()


def test_profile_opens_backup_read_only(tmp_path: Path) -> None:
    backup_home = tmp_path / "backup"
    db = backup_home / "state" / "studio.db"
    _write_backup_db(db)

    conn = connect_backup_readonly(backup_home)
    profile = profile_canonical_events(conn)
    assert profile["read_only"] is True
    assert profile["row_count"] == 5
    try:
        conn.execute("CREATE TABLE should_fail(id TEXT)")
    except sqlite3.OperationalError as exc:
        assert "readonly" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("backup connection accepted a write")
    conn.close()


def test_dry_run_classifies_high_confidence_duplicates_and_manual(tmp_path: Path) -> None:
    backup_home = tmp_path / "backup"
    active_home = tmp_path / "active"
    _write_backup_db(backup_home / "state" / "studio.db")
    active_db = active_home / "state" / "studio.db"
    active_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(active_db)
    run_migrations(conn)
    ensure_import_map_table(conn)
    conn.execute("""
        INSERT INTO hook_invocations (
            invocation_id, hook_id, status, prevented_risky_action
        ) VALUES ('legacy-hook-execution-2', 'on_pulse', 'success', 0)
        """)
    conn.commit()
    backup_conn = connect_backup_readonly(backup_home)
    plan = build_import_plan(backup_conn, conn)
    statuses = {(entry.legacy_event_id, entry.target_table): entry.import_status for entry in plan}
    assert statuses[("skill-1", "execution_events")] == "pending_import"
    assert statuses[("skill-1", "skill_invocations")] == "pending_import"
    assert statuses[("hook-duplicate", "hook_invocations")] == "skipped_duplicate"
    assert statuses[("validation-noise", None)] == "retention_only"
    assert statuses[("token-raw", "token_usage_records")] == "pending_import"
    assert statuses[("token-manual", None)] == "manual_review_required"
    backup_conn.close()
    conn.close()


def test_apply_imports_only_high_confidence_and_keeps_source_refs(tmp_path: Path) -> None:
    backup_home = tmp_path / "backup"
    active_home = tmp_path / "active"
    _write_backup_db(backup_home / "state" / "studio.db")
    active_db = active_home / "state" / "studio.db"
    active_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(active_db)
    run_migrations(conn)
    conn.close()

    result = run_reconciliation(
        backup_home=backup_home,
        active_home=active_home,
        apply=True,
    )
    assert result["validation"]["valid"] is True
    conn = sqlite3.connect(active_db)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM legacy_canonical_event_import_map WHERE import_status = 'imported'"
        ).fetchone()[0]
        == 5
    )
    refs = conn.execute("""
        SELECT source_refs_json
        FROM execution_events
        WHERE event_id LIKE 'legacy-canonical-event-%'
        """).fetchall()
    assert refs
    assert all("backup:canonical_events:" in row[0] for row in refs)
    token_ref = conn.execute("""
        SELECT source_refs_json, purpose, total_tokens, provider
        FROM token_usage_records
        WHERE token_usage_id = 'legacy-raw-token-501'
        """).fetchone()
    assert token_ref is not None
    assert "backup:canonical_events:token-raw" in token_ref[0]
    assert "cost unavailable" in token_ref[1]
    assert token_ref[2] == 3
    assert token_ref[3] == "anthropic"
    assert validate_reconciliation(conn)["valid"] is True
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='canonical_events'"
        ).fetchone()[0]
        == 0
    )
    conn.close()
