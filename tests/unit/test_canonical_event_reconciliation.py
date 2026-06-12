from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.upgrade.canonical_event_reconciliation import (
    connect_backup_readonly,
    profile_canonical_events,
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
